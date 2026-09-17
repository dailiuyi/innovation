CREATE FUNCTION require_admin(p_actor uuid) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM admin_user WHERE id=p_actor AND enabled) THEN RAISE EXCEPTION 'admin required'; END IF;
END $$;
CREATE FUNCTION version_was_published(p_version uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM audit_log WHERE action='PUBLISH_VERSION' AND detail->>'versionId'=p_version::text);
$$;
CREATE FUNCTION seal_version(p_version uuid,p_expected bigint,p_actor uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE v scene_version;
BEGIN
 PERFORM require_admin(p_actor);
 SELECT * INTO STRICT v FROM scene_version WHERE id=p_version FOR UPDATE;
 IF v.state<>'DRAFT' OR v.lock_version<>p_expected THEN RAISE EXCEPTION 'version conflict'; END IF;
 UPDATE scene_version SET state='READY' WHERE id=p_version;
 INSERT INTO audit_log(actor_id,action,object_id) VALUES(p_actor,'SEAL_VERSION',p_version);
END $$;
CREATE FUNCTION publish_version(p_scene uuid,p_variant text,p_version uuid,p_expected bigint,p_actor uuid,p_reason text)
 RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE s scene; old_id uuid;
BEGIN
 PERFORM require_admin(p_actor);
 IF p_variant NOT IN ('DAY','NIGHT') OR p_variant IS NULL THEN RAISE EXCEPTION 'invalid variant'; END IF;
 IF p_reason IS NULL OR btrim(p_reason)='' THEN RAISE EXCEPTION 'reason required'; END IF;
 SELECT * INTO STRICT s FROM scene WHERE id=p_scene FOR UPDATE;
 IF s.lock_version<>p_expected THEN RAISE EXCEPTION 'scene version conflict'; END IF;
 IF p_version IS NOT NULL AND (NOT version_is_servable(p_version) OR NOT EXISTS(SELECT 1 FROM scene_version
   WHERE id=p_version AND scene_id=p_scene AND variant=p_variant)) THEN RAISE EXCEPTION 'version not publishable'; END IF;
 old_id:=CASE WHEN p_variant='DAY' THEN s.current_day_version_id ELSE s.current_night_version_id END;
 UPDATE scene SET current_day_version_id=CASE WHEN p_variant='DAY' THEN p_version ELSE current_day_version_id END,
   current_night_version_id=CASE WHEN p_variant='NIGHT' THEN p_version ELSE current_night_version_id END,
   lock_version=lock_version+1 WHERE id=p_scene;
 INSERT INTO audit_log(actor_id,action,object_id,detail) VALUES(p_actor,'PUBLISH_VERSION',p_scene,
   jsonb_build_object('variant',p_variant,'previousVersionId',old_id,'versionId',p_version,'reason',p_reason));
 RETURN s.lock_version+1;
END $$;
