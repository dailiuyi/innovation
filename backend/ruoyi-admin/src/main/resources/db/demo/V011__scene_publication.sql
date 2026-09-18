-- One published draft pointer per scene. Freeze is derived from this pointer.
ALTER TABLE ar_scene ADD COLUMN published_draft_id uuid REFERENCES ar_draft(id);
ALTER TABLE ar_scene ADD COLUMN published_at timestamptz;
ALTER TABLE ar_scene ADD COLUMN published_by_id bigint REFERENCES sys_user(user_id);
ALTER TABLE ar_scene ADD COLUMN published_by_name varchar(30);
ALTER TABLE ar_scene ADD CONSTRAINT ar_scene_published_ck CHECK (
    (published_draft_id IS NULL AND published_at IS NULL AND published_by_id IS NULL AND published_by_name IS NULL)
    OR (published_draft_id IS NOT NULL AND published_at IS NOT NULL AND published_by_id IS NOT NULL AND published_by_name IS NOT NULL)
);
CREATE UNIQUE INDEX ar_scene_published_draft_uidx ON ar_scene(published_draft_id) WHERE published_draft_id IS NOT NULL;
CREATE FUNCTION ar_scene_published_draft_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.published_draft_id IS NULL THEN RETURN NEW; END IF;
    IF NOT EXISTS (SELECT 1 FROM ar_draft WHERE id=NEW.published_draft_id AND scene_id=NEW.id) THEN
        RAISE EXCEPTION 'published draft must belong to the scene';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ar_scene_published_draft_guard BEFORE INSERT OR UPDATE OF published_draft_id ON ar_scene
    FOR EACH ROW EXECUTE FUNCTION ar_scene_published_draft_guard();
