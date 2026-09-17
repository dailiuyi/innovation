ALTER TABLE sys_user ADD COLUMN credential_epoch bigint NOT NULL DEFAULT 0;
CREATE FUNCTION demo_bump_credential_epoch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.password IS DISTINCT FROM OLD.password OR NEW.status IS DISTINCT FROM OLD.status THEN
        NEW.credential_epoch := OLD.credential_epoch + 1;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER demo_credential_epoch BEFORE UPDATE ON sys_user
FOR EACH ROW EXECUTE FUNCTION demo_bump_credential_epoch();
