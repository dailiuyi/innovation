-- File collections, export relative paths, and ZIP cache. Storage bytes stay UUID.bin.
CREATE TABLE ar_draft_collection (
    id uuid PRIMARY KEY,
    draft_id uuid NOT NULL REFERENCES ar_draft(id),
    request_key uuid NOT NULL,
    status varchar(20) NOT NULL CHECK(status IN ('PENDING','ACTIVE','RETIRED','CANCELLED')),
    generation bigint NOT NULL DEFAULT 1 CHECK(generation >= 1),
    file_count integer NOT NULL CHECK(file_count >= 0),
    total_bytes bigint NOT NULL CHECK(total_bytes >= 0),
    fingerprint varchar(64) NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
    creator_id bigint NOT NULL REFERENCES sys_user(user_id),
    creator_name varchar(30) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(draft_id, request_key)
);
CREATE UNIQUE INDEX ar_draft_collection_active_uidx ON ar_draft_collection(draft_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX ar_draft_collection_pending_uidx ON ar_draft_collection(draft_id) WHERE status = 'PENDING';
CREATE INDEX ar_draft_collection_draft_idx ON ar_draft_collection(draft_id, status);

INSERT INTO ar_draft_collection(id, draft_id, request_key, status, generation, file_count, total_bytes, fingerprint, creator_id, creator_name)
SELECT gen_random_uuid(), d.id, gen_random_uuid(), 'ACTIVE', 1,
    (SELECT count(*) FROM ar_draft_file f WHERE f.draft_id = d.id AND f.removed_at IS NULL),
    (SELECT coalesce(sum(f.expected_bytes), 0) FROM ar_draft_file f WHERE f.draft_id = d.id AND f.removed_at IS NULL),
    repeat('0', 64), d.creator_id, d.creator_name
FROM ar_draft d
WHERE EXISTS (SELECT 1 FROM ar_draft_file f WHERE f.draft_id = d.id);

ALTER TABLE ar_draft_file ADD COLUMN collection_id uuid REFERENCES ar_draft_collection(id);
ALTER TABLE ar_draft_file ADD COLUMN relative_path varchar(1024);

UPDATE ar_draft_file f SET collection_id = c.id
FROM ar_draft_collection c
WHERE c.draft_id = f.draft_id AND c.status = 'ACTIVE';

WITH numbered AS (
    SELECT id, file_name,
        row_number() OVER (PARTITION BY draft_id, lower(file_name) ORDER BY created_at, id) AS rn
    FROM ar_draft_file
)
UPDATE ar_draft_file f SET relative_path = CASE
    WHEN n.rn = 1 THEN n.file_name
    WHEN n.file_name ~ '\.[^./]+$' THEN regexp_replace(n.file_name, '(\.[^./]+)$', '-' || left(f.id::text, 8) || '\1')
    ELSE n.file_name || '-' || left(f.id::text, 8)
END
FROM numbered n
WHERE f.id = n.id;

ALTER TABLE ar_draft_file ALTER COLUMN collection_id SET NOT NULL;
ALTER TABLE ar_draft_file ALTER COLUMN relative_path SET NOT NULL;
ALTER TABLE ar_draft_file ADD CONSTRAINT ar_draft_file_relative_path_ck CHECK (
    char_length(relative_path) BETWEEN 1 AND 1024 AND position('/' in relative_path) <> 1 AND relative_path !~ '[\\]'
);
CREATE UNIQUE INDEX ar_draft_file_path_uidx ON ar_draft_file(collection_id, relative_path) WHERE removed_at IS NULL;
ALTER TABLE ar_draft_file DROP CONSTRAINT ar_draft_file_draft_id_request_key_key;
CREATE UNIQUE INDEX ar_draft_file_collection_request_uidx ON ar_draft_file(collection_id, request_key);
CREATE INDEX ar_draft_file_collection_idx ON ar_draft_file(collection_id, status);
ALTER TABLE ar_file_deletion DROP CONSTRAINT ar_file_deletion_draft_id_request_key_key;
CREATE INDEX ar_file_deletion_draft_request_idx ON ar_file_deletion(draft_id, request_key);

CREATE TABLE ar_zip_export (
    id uuid PRIMARY KEY,
    collection_id uuid NOT NULL REFERENCES ar_draft_collection(id),
    generation bigint NOT NULL CHECK(generation >= 1),
    bytes bigint,
    sha256 varchar(64),
    status varchar(20) NOT NULL CHECK(status IN ('PREPARING','AVAILABLE','FAILED')),
    failure_reason varchar(500),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    last_accessed_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    CHECK((status = 'AVAILABLE' AND bytes IS NOT NULL AND bytes >= 0 AND sha256 IS NOT NULL AND sha256 ~ '^[0-9a-f]{64}$'
            AND completed_at IS NOT NULL AND failure_reason IS NULL)
        OR (status = 'PREPARING' AND bytes IS NULL AND sha256 IS NULL AND completed_at IS NULL AND failure_reason IS NULL)
        OR (status = 'FAILED' AND failure_reason IS NOT NULL))
);
CREATE UNIQUE INDEX ar_zip_export_live_uidx ON ar_zip_export(collection_id, generation) WHERE status IN ('PREPARING','AVAILABLE');
CREATE INDEX ar_zip_export_collection_idx ON ar_zip_export(collection_id);
