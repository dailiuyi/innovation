-- V012 copied file_name into relative_path for pre-folder rows. Folder uploads already
-- store nested relative_path. Rewrite only unsafe or conflicting export paths.
-- Keep original file_name and storage bytes. Drop the unique index while rewriting so
-- intermediate names cannot fail the migration. Daily Demo is on V012; this migration
-- has not been applied to a preserved database.
CREATE FUNCTION ar_relative_path_ok(p text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    n text;
    parts text[];
    seg text;
BEGIN
    IF p IS NULL OR p = '' THEN RETURN false; END IF;
    IF char_length(p) > 1024 THEN RETURN false; END IF;
    IF p ~ '[\\]' OR p LIKE '/%' OR p LIKE '%/' OR p LIKE '%//' THEN RETURN false; END IF;
    IF char_length(p) >= 2 AND substring(p from 1 for 1) ~ '[A-Za-z]' AND substring(p from 2 for 1) = ':' THEN
        RETURN false;
    END IF;
    n := normalize(p, NFC);
    IF n LIKE '/%' OR n LIKE '%/' OR n LIKE '%//' THEN RETURN false; END IF;
    parts := string_to_array(n, '/');
    IF coalesce(array_length(parts, 1), 0) = 0 OR coalesce(array_length(parts, 1), 0) > 32 THEN
        RETURN false;
    END IF;
    FOREACH seg IN ARRAY parts LOOP
        IF seg IS NULL OR seg = '' OR char_length(seg) > 255 THEN RETURN false; END IF;
        IF seg IN ('.', '..') THEN RETURN false; END IF;
        IF seg ~ '^ ' OR seg ~ ' $' OR seg ~ '\.$' THEN RETURN false; END IF;
        IF seg ~ E'[\\x01-\\x1f\\x7f]' OR seg ~ '[<>:"|?*]' THEN RETURN false; END IF;
        IF seg ~* '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$' THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END $$;

CREATE FUNCTION ar_safe_export_path(p text, file_id uuid) RETURNS text
    LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    n text;
    parts text[];
    seg text;
    cleaned text;
    ext text;
    out_parts text[] := ARRAY[]::text[];
    result text;
BEGIN
    IF p IS NULL OR p = '' THEN
        RETURN 'export-' || left(file_id::text, 8);
    END IF;
    n := normalize(replace(p, '\', '/'), NFC);
    n := regexp_replace(n, '^/+', '');
    n := regexp_replace(n, '/+$', '');
    n := regexp_replace(n, '/{2,}', '/', 'g');
    parts := string_to_array(n, '/');
    IF coalesce(array_length(parts, 1), 0) = 0 OR coalesce(array_length(parts, 1), 0) > 32 THEN
        RETURN 'export-' || left(file_id::text, 8);
    END IF;
    FOREACH seg IN ARRAY parts LOOP
        IF seg IS NULL OR seg IN ('', '.', '..') THEN
            CONTINUE;
        END IF;
        cleaned := regexp_replace(seg, '[<>:"|?*]', '_', 'g');
        cleaned := regexp_replace(cleaned, E'[\\x01-\\x1f\\x7f]', '_', 'g');
        cleaned := regexp_replace(cleaned, '^ +', '');
        cleaned := regexp_replace(cleaned, '[. ]+$', '');
        IF cleaned = '' OR cleaned IN ('.', '..')
            OR cleaned ~* '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$' THEN
            ext := substring(seg from '\.[A-Za-z0-9]{1,20}$');
            cleaned := 'export-' || left(file_id::text, 8) || coalesce(ext, '');
        END IF;
        IF char_length(cleaned) > 255 THEN
            cleaned := regexp_replace(left(cleaned, 255), '[. ]+$', '');
        END IF;
        IF cleaned = '' THEN
            cleaned := 'export-' || left(file_id::text, 8);
        END IF;
        out_parts := out_parts || cleaned;
    END LOOP;
    IF coalesce(array_length(out_parts, 1), 0) = 0 OR coalesce(array_length(out_parts, 1), 0) > 32 THEN
        RETURN 'export-' || left(file_id::text, 8);
    END IF;
    result := array_to_string(out_parts, '/');
    IF char_length(result) > 1024 OR NOT ar_relative_path_ok(result) THEN
        ext := substring(p from '\.[A-Za-z0-9]{1,20}$');
        RETURN 'export-' || left(file_id::text, 8) || coalesce(ext, '');
    END IF;
    RETURN result;
END $$;

DROP INDEX IF EXISTS ar_draft_file_path_uidx;

DO $$
DECLARE
    r record;
    cand text;
    folded text;
    parent text;
    last_seg text;
    stem text;
    ext text;
    trial text;
    suffix text;
    suffixes text[];
    taken boolean;
BEGIN
    CREATE TEMP TABLE ar_v013_taken (
        collection_id uuid NOT NULL,
        path_lower text NOT NULL,
        PRIMARY KEY (collection_id, path_lower)
    ) ON COMMIT DROP;
    CREATE TEMP TABLE ar_v013_rewrite (
        id uuid PRIMARY KEY
    ) ON COMMIT DROP;

    FOR r IN
        SELECT id, collection_id, relative_path
        FROM ar_draft_file
        WHERE removed_at IS NULL
        ORDER BY collection_id, id
    LOOP
        folded := lower(normalize(r.relative_path, NFC));
        IF ar_relative_path_ok(r.relative_path) AND NOT EXISTS (
            SELECT 1 FROM ar_v013_taken t
            WHERE t.collection_id = r.collection_id
              AND (t.path_lower = folded
                   OR starts_with(t.path_lower, folded || '/')
                   OR starts_with(folded, t.path_lower || '/'))
        ) THEN
            INSERT INTO ar_v013_taken VALUES (r.collection_id, folded);
        ELSE
            INSERT INTO ar_v013_rewrite VALUES (r.id);
        END IF;
    END LOOP;

    FOR r IN
        SELECT f.id, f.collection_id, f.relative_path
        FROM ar_draft_file f
        JOIN ar_v013_rewrite w ON w.id = f.id
        ORDER BY f.collection_id, f.id
    LOOP
        cand := ar_safe_export_path(r.relative_path, r.id);
        folded := lower(normalize(cand, NFC));
        taken := EXISTS (
            SELECT 1 FROM ar_v013_taken t
            WHERE t.collection_id = r.collection_id
              AND (t.path_lower = folded
                   OR starts_with(t.path_lower, folded || '/')
                   OR starts_with(folded, t.path_lower || '/'))
        );
        IF NOT ar_relative_path_ok(cand) OR taken THEN
            last_seg := regexp_replace(cand, '^.*/', '');
            IF position('/' in cand) > 0 THEN
                parent := left(cand, length(cand) - length(last_seg) - 1);
            ELSE
                parent := NULL;
            END IF;
            ext := substring(last_seg from '\.[A-Za-z0-9]{1,20}$');
            stem := CASE WHEN ext IS NULL THEN last_seg ELSE left(last_seg, length(last_seg) - length(ext)) END;
            suffixes := ARRAY[left(r.id::text, 8), replace(r.id::text, '-', ''), r.id::text];
            cand := NULL;
            FOREACH suffix IN ARRAY suffixes LOOP
                trial := stem || '-' || suffix || coalesce(ext, '');
                IF char_length(trial) > 255 THEN
                    trial := left(stem, greatest(1, 255 - 1 - length(suffix) - coalesce(length(ext), 0)))
                        || '-' || suffix || coalesce(ext, '');
                    trial := regexp_replace(trial, '[. ]+$', '');
                END IF;
                IF parent IS NOT NULL THEN
                    trial := parent || '/' || trial;
                END IF;
                IF char_length(trial) > 1024 OR NOT ar_relative_path_ok(trial) THEN
                    CONTINUE;
                END IF;
                folded := lower(normalize(trial, NFC));
                IF NOT EXISTS (
                    SELECT 1 FROM ar_v013_taken t
                    WHERE t.collection_id = r.collection_id
                      AND (t.path_lower = folded
                           OR starts_with(t.path_lower, folded || '/')
                           OR starts_with(folded, t.path_lower || '/'))
                ) THEN
                    cand := trial;
                    EXIT;
                END IF;
            END LOOP;
            IF cand IS NULL THEN
                cand := 'export-' || replace(r.id::text, '-', '');
            END IF;
        END IF;
        UPDATE ar_draft_file SET relative_path = cand WHERE id = r.id;
        INSERT INTO ar_v013_taken VALUES (r.collection_id, lower(normalize(cand, NFC)));
    END LOOP;
END $$;

CREATE UNIQUE INDEX ar_draft_file_path_uidx ON ar_draft_file(collection_id, relative_path) WHERE removed_at IS NULL;
