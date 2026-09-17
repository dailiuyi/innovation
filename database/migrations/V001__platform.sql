-- V0.1 initial schema, PostgreSQL 17+. No seed credentials.
CREATE TABLE admin_user (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), login varchar(100) NOT NULL UNIQUE,
 display_name varchar(100) NOT NULL, password_hash text NOT NULL,
 enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE scene (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name varchar(200) NOT NULL, address text,
 longitude numeric(10,7), latitude numeric(9,7),
 geo_crs varchar(10) NOT NULL DEFAULT 'WGS84' CHECK(geo_crs IN ('WGS84','GCJ02','BD09')),
 enabled boolean NOT NULL DEFAULT true, current_day_version_id uuid, current_night_version_id uuid,
 lock_version bigint NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(longitude BETWEEN -180 AND 180), CHECK(latitude BETWEEN -90 AND 90),
 CHECK((longitude IS NULL)=(latitude IS NULL))
);
CREATE TABLE scene_version (
 id uuid PRIMARY KEY, scene_id uuid NOT NULL REFERENCES scene(id),
 variant varchar(10) NOT NULL CHECK(variant IN ('DAY','NIGHT')), version_no integer NOT NULL CHECK(version_no>0),
 state varchar(10) NOT NULL DEFAULT 'DRAFT' CHECK(state IN ('DRAFT','READY','REVOKED')),
 packages jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(packages)='object'),
 playback jsonb NOT NULL DEFAULT '{"mode":"LOCAL_INDEPENDENT","durationMs":0,"recoveryPolicy":"RESUME_LOCAL_TIME"}' CHECK(jsonb_typeof(playback)='object'),
 note text NOT NULL DEFAULT '', lock_version bigint NOT NULL DEFAULT 0,
 created_by uuid NOT NULL REFERENCES admin_user(id), created_at timestamptz NOT NULL DEFAULT now(), ready_at timestamptz,
 UNIQUE(scene_id,id), UNIQUE(scene_id,variant,version_no), CHECK(state='DRAFT' OR ready_at IS NOT NULL)
);
ALTER TABLE scene ADD FOREIGN KEY(id,current_day_version_id) REFERENCES scene_version(scene_id,id);
ALTER TABLE scene ADD FOREIGN KEY(id,current_night_version_id) REFERENCES scene_version(scene_id,id);
CREATE TABLE asset (
 id uuid PRIMARY KEY, kind varchar(20) NOT NULL CHECK(kind IN ('CAPTURE','GS','MODEL','TEXTURE','AUDIO','TIMELINE','BUNDLE','MANIFEST','OTHER')),
 state varchar(10) NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','READY','REJECTED','REVOKED')),
 upload_key text NOT NULL UNIQUE, object_key text NOT NULL UNIQUE, content_type varchar(160) NOT NULL,
 expected_bytes bigint NOT NULL CHECK(expected_bytes>0), expected_sha256 char(64) NOT NULL CHECK(expected_sha256 ~ '^[0-9a-f]{64}$'),
 verified_bytes bigint, verified_sha256 char(64), created_by uuid NOT NULL REFERENCES admin_user(id), created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(state NOT IN ('READY','REVOKED') OR (verified_bytes IS NOT NULL AND verified_bytes=expected_bytes
   AND verified_sha256 IS NOT NULL AND verified_sha256=expected_sha256))
);
CREATE TABLE version_asset (
 version_id uuid NOT NULL REFERENCES scene_version(id), asset_id uuid NOT NULL REFERENCES asset(id),
 platform varchar(20) NOT NULL CHECK(platform IN ('ANDROID','IOS','MINIPROGRAM')),
 logical_path text NOT NULL CHECK(logical_path<>'' AND logical_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
 PRIMARY KEY(version_id,platform,logical_path)
);
CREATE TABLE marker (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), scene_id uuid NOT NULL REFERENCES scene(id), code varchar(100) NOT NULL UNIQUE,
 width_m numeric(9,6) NOT NULL CHECK(width_m>0), height_m numeric(9,6) NOT NULL CHECK(height_m>0),
 x numeric(14,6) NOT NULL, y numeric(14,6) NOT NULL, z numeric(14,6) NOT NULL,
 qx numeric(12,9) NOT NULL, qy numeric(12,9) NOT NULL, qz numeric(12,9) NOT NULL, qw numeric(12,9) NOT NULL,
 enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(abs(qx*qx+qy*qy+qz*qz+qw*qw-1)<0.00001), CHECK(abs(x)<100000 AND abs(y)<100000 AND abs(z)<100000)
);
CREATE TABLE audit_log (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), actor_id uuid NOT NULL REFERENCES admin_user(id),
 action varchar(50) NOT NULL, object_id uuid NOT NULL, detail jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX version_scene ON scene_version(scene_id,variant,version_no DESC);
CREATE INDEX version_asset_reverse ON version_asset(asset_id);
CREATE INDEX marker_scene ON marker(scene_id);
CREATE INDEX asset_state ON asset(state,created_at DESC);
CREATE INDEX audit_object ON audit_log(object_id,created_at DESC);
CREATE FUNCTION guard_version_asset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s text;
BEGIN
 IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'replace draft associations with delete/insert'; END IF;
 SELECT state INTO s FROM scene_version WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.version_id ELSE NEW.version_id END FOR UPDATE;
 IF s IS DISTINCT FROM 'DRAFT' THEN RAISE EXCEPTION 'version files are frozen'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER version_asset_guard BEFORE INSERT OR UPDATE OR DELETE ON version_asset FOR EACH ROW EXECUTE FUNCTION guard_version_asset();
CREATE FUNCTION guard_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item record;
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.state<>'DRAFT' THEN RAISE EXCEPTION 'create draft first'; END IF;
   RETURN NEW;
 END IF;
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'retain version history'; END IF;
 IF (NEW.id,NEW.scene_id,NEW.variant,NEW.version_no,NEW.created_by,NEW.created_at) IS DISTINCT FROM
    (OLD.id,OLD.scene_id,OLD.variant,OLD.version_no,OLD.created_by,OLD.created_at) THEN RAISE EXCEPTION 'version identity immutable'; END IF;
 IF OLD.state<>'DRAFT' THEN
   IF (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') OR
      (NEW.state<>OLD.state AND NOT(OLD.state='READY' AND NEW.state='REVOKED')) THEN RAISE EXCEPTION 'ready version immutable'; END IF;
   RETURN NEW;
 END IF;
 IF NEW.state='REVOKED' THEN RAISE EXCEPTION 'only ready versions can be revoked'; END IF;
 IF NEW.state='READY' THEN
   IF NEW.packages='{}' THEN RAISE EXCEPTION 'platform package required'; END IF;
   IF EXISTS(SELECT 1 FROM version_asset va JOIN asset a ON a.id=va.asset_id WHERE va.version_id=NEW.id AND a.state<>'READY') THEN RAISE EXCEPTION 'file not verified'; END IF;
   FOR item IN SELECT * FROM jsonb_each(NEW.packages) LOOP
     IF item.key NOT IN ('ANDROID','IOS','MINIPROGRAM') OR jsonb_typeof(item.value)<>'object'
       OR NOT(item.value ?& ARRAY['format','runtimeVersion','minClientBuild','entrypoint']) THEN RAISE EXCEPTION 'invalid platform configuration'; END IF;
     IF NOT EXISTS(SELECT 1 FROM version_asset WHERE version_id=NEW.id AND platform=item.key
       AND logical_path=item.value->>'entrypoint') THEN RAISE EXCEPTION 'entrypoint missing'; END IF;
   END LOOP;
   IF EXISTS(SELECT 1 FROM version_asset WHERE version_id=NEW.id AND NOT(NEW.packages ? platform)) THEN RAISE EXCEPTION 'undeclared platform files'; END IF;
   NEW.ready_at:=now();
 END IF;
 NEW.lock_version:=OLD.lock_version+1;
 RETURN NEW;
END $$;
CREATE TRIGGER version_guard BEFORE INSERT OR UPDATE OR DELETE ON scene_version FOR EACH ROW EXECUTE FUNCTION guard_version();
CREATE FUNCTION guard_asset() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'retain asset metadata'; END IF;
 IF OLD.state IN ('READY','REVOKED') AND ((to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') OR
   (NEW.state<>OLD.state AND NOT(OLD.state='READY' AND NEW.state='REVOKED'))) THEN RAISE EXCEPTION 'verified asset immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER asset_guard BEFORE UPDATE OR DELETE ON asset FOR EACH ROW EXECUTE FUNCTION guard_asset();
CREATE FUNCTION guard_marker() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-'enabled') IS DISTINCT FROM (to_jsonb(OLD)-'enabled') THEN RAISE EXCEPTION 'replace physical marker instead of changing its geometry'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER marker_guard BEFORE UPDATE ON marker FOR EACH ROW EXECUTE FUNCTION guard_marker();
CREATE FUNCTION version_is_servable(p_version uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM scene_version WHERE id=p_version AND state='READY')
 AND EXISTS(SELECT 1 FROM version_asset WHERE version_id=p_version)
 AND NOT EXISTS(SELECT 1 FROM version_asset va JOIN asset a ON a.id=va.asset_id WHERE va.version_id=p_version AND a.state<>'READY');
$$;
CREATE FUNCTION guard_current_versions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.current_day_version_id IS DISTINCT FROM OLD.current_day_version_id AND NEW.current_day_version_id IS NOT NULL THEN
   IF NOT version_is_servable(NEW.current_day_version_id) OR NOT EXISTS(SELECT 1 FROM scene_version
     WHERE id=NEW.current_day_version_id AND scene_id=NEW.id AND variant='DAY') THEN RAISE EXCEPTION 'invalid day version'; END IF;
 END IF;
 IF NEW.current_night_version_id IS DISTINCT FROM OLD.current_night_version_id AND NEW.current_night_version_id IS NOT NULL THEN
   IF NOT version_is_servable(NEW.current_night_version_id) OR NOT EXISTS(SELECT 1 FROM scene_version
     WHERE id=NEW.current_night_version_id AND scene_id=NEW.id AND variant='NIGHT') THEN RAISE EXCEPTION 'invalid night version'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER current_versions_guard BEFORE UPDATE ON scene FOR EACH ROW EXECUTE FUNCTION guard_current_versions();
CREATE FUNCTION audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit is append only'; END $$;
CREATE TRIGGER audit_guard BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_append_only();
