-- Durable deletion receipts: no file content. Completed receipts prevent stale retry resurrection.
-- Do not convert earlier logical removals into deletion requests automatically.
CREATE TABLE ar_file_deletion (
    file_id uuid PRIMARY KEY,
    draft_id uuid NOT NULL REFERENCES ar_draft(id),
    request_key uuid NOT NULL,
    actor_id bigint NOT NULL REFERENCES sys_user(user_id),
    actor_name varchar(30) NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    failure_reason varchar(500),
    UNIQUE(draft_id, request_key),
    CHECK(completed_at IS NULL OR failure_reason IS NULL)
);
CREATE INDEX ar_file_deletion_pending_idx ON ar_file_deletion(file_id) WHERE completed_at IS NULL;
