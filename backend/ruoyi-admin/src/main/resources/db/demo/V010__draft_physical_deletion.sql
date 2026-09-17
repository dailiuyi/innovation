-- Draft rows may be removed after every file has a deletion receipt.
-- Receipts stay for idempotency and audit; they no longer require the draft row.
ALTER TABLE ar_file_deletion DROP CONSTRAINT ar_file_deletion_draft_id_fkey;
