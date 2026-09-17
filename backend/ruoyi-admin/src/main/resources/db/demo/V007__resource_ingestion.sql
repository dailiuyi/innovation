-- Drafts and private files only; no publication or client-loading contract.
CREATE TABLE ar_draft (
    id uuid PRIMARY KEY,
    scene_id uuid NOT NULL REFERENCES ar_scene(id),
    request_key uuid NOT NULL,
    description varchar(2000) NOT NULL DEFAULT '',
    lock_version bigint NOT NULL DEFAULT 0 CHECK(lock_version >= 0),
    creator_id bigint NOT NULL REFERENCES sys_user(user_id),
    creator_name varchar(30) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(scene_id, request_key)
);
CREATE INDEX ar_draft_scene_idx ON ar_draft(scene_id, created_at DESC, id);
CREATE TABLE ar_draft_file (
    id uuid PRIMARY KEY,
    draft_id uuid NOT NULL REFERENCES ar_draft(id),
    request_key uuid NOT NULL,
    file_name varchar(255) NOT NULL CHECK(length(trim(file_name)) > 0),
    kind varchar(30) NOT NULL CHECK(kind IN ('RESOURCE_FILE','CLIENT_LIBRARY')),
    expected_bytes bigint NOT NULL CHECK(expected_bytes >= 0),
    expected_sha256 varchar(64) NOT NULL CHECK(expected_sha256 ~ '^[0-9a-f]{64}$'),
    storage_key varchar(40) NOT NULL UNIQUE CHECK(storage_key = id::text || '.bin'),
    status varchar(20) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','UPLOADING','AVAILABLE','FAILED')),
    verified_bytes bigint,
    verified_sha256 varchar(64),
    failure_reason varchar(500),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    creator_id bigint NOT NULL REFERENCES sys_user(user_id),
    creator_name varchar(30) NOT NULL,
    last_actor_id bigint NOT NULL REFERENCES sys_user(user_id),
    last_actor_name varchar(30) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(draft_id, request_key),
    CHECK((status = 'AVAILABLE' AND verified_bytes IS NOT NULL AND verified_bytes = expected_bytes
        AND verified_sha256 IS NOT NULL AND verified_sha256 = expected_sha256 AND failure_reason IS NULL)
        OR (status <> 'AVAILABLE' AND verified_bytes IS NULL AND verified_sha256 IS NULL)),
    CHECK(status <> 'FAILED' OR failure_reason IS NOT NULL)
);
CREATE INDEX ar_draft_file_draft_idx ON ar_draft_file(draft_id, created_at, id);
