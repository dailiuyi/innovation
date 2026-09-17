CREATE TABLE ar_scene (
    id uuid PRIMARY KEY,
    name varchar(200) NOT NULL CHECK(length(trim(name))>0),
    address varchar(1000),
    longitude numeric CHECK(longitude BETWEEN -180 AND 180),
    latitude numeric CHECK(latitude BETWEEN -90 AND 90),
    geo_crs varchar(10),
    enabled boolean NOT NULL DEFAULT true,
    lock_version bigint NOT NULL DEFAULT 0 CHECK(lock_version>=0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((longitude IS NULL AND latitude IS NULL AND geo_crs IS NULL)
        OR (longitude IS NOT NULL AND latitude IS NOT NULL AND geo_crs IS NOT NULL AND geo_crs IN ('WGS84','GCJ02','BD09')))
);
CREATE INDEX ar_scene_created_idx ON ar_scene(created_at DESC,id);
CREATE TABLE ar_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scene_id uuid NOT NULL REFERENCES ar_scene(id),
    actor_id bigint NOT NULL REFERENCES sys_user(user_id),
    actor_name varchar(30) NOT NULL,
    action varchar(30) NOT NULL,
    detail jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ar_audit_scene_idx ON ar_audit(scene_id,id DESC);
CREATE FUNCTION ar_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit records are append-only'; END $$;
CREATE TRIGGER ar_audit_immutable BEFORE UPDATE OR DELETE ON ar_audit FOR EACH ROW EXECUTE FUNCTION ar_audit_immutable();
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon) VALUES
(2010,'场景管理',2000,0,'scenes','demo/scenes','C','0','0','ar:scene:list','tree'),
(2011,'场景操作记录',2000,1,'audits','demo/audits','C','0','0','ar:audit:list','form');
INSERT INTO sys_role_menu(role_id,menu_id) VALUES(100,2010),(100,2011);
