-- Logical removal only. Keep bytes, identity and idempotency keys for audit.
ALTER TABLE ar_draft_file ADD COLUMN removed_at timestamptz;
ALTER TABLE ar_draft_file ADD COLUMN removed_by bigint REFERENCES sys_user(user_id);
ALTER TABLE ar_draft_file ADD CONSTRAINT ar_file_removal_actor CHECK ((removed_at IS NULL) = (removed_by IS NULL));
