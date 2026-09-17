package com.ruoyi.ar;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.ar.storage.ArtifactStorage;
import com.ruoyi.common.utils.SecurityUtils;
import java.io.IOException;
import java.io.InputStream;
import java.util.*;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

/** One application instance and one private local volume. No background upload worker. */
@Service
@DependsOnDatabaseInitialization
@ConditionalOnProperty(name="ar.storage.enabled", havingValue="true")
public class DraftService implements InitializingBean {
    private static final String DRAFT_COLUMNS = "id::text as id, scene_id::text as \"sceneId\", description, lock_version as \"lockVersion\", creator_id as \"creatorId\", creator_name as \"creatorName\", created_at as \"createdAt\", updated_at as \"updatedAt\"";
    private static final String FILE_COLUMNS = "id::text as id, draft_id::text as \"draftId\", file_name as \"fileName\", kind, expected_bytes as bytes, expected_sha256 as sha256, storage_key as \"storageKey\", case when exists(select 1 from ar_file_deletion d where d.file_id=ar_draft_file.id and d.completed_at is null) then case when (select d.failure_reason from ar_file_deletion d where d.file_id=ar_draft_file.id) is null then 'DELETING' else 'DELETE_FAILED' end else status end as status, verified_bytes as \"verifiedBytes\", verified_sha256 as \"verifiedSha256\", coalesce((select d.failure_reason from ar_file_deletion d where d.file_id=ar_draft_file.id),failure_reason) as \"failureReason\", attempts, creator_id as \"creatorId\", creator_name as \"creatorName\", last_actor_id as \"lastActorId\", last_actor_name as \"lastActorName\", created_at as \"createdAt\", updated_at as \"updatedAt\"";
    private final JdbcTemplate db;
    private final TransactionTemplate tx;
    private final ArtifactStorage storage;
    private final ObjectMapper json;
    private final long maxBytes;
    // Bounded lock set; never remove a lock while another request can still own it.
    private final ReentrantLock[] locks = new ReentrantLock[256];

    public DraftService(JdbcTemplate db,PlatformTransactionManager transactions,ArtifactStorage storage,
            ObjectMapper json,@Value("${ar.storage.max-bytes}") long maxBytes) {
        this.db=db; this.tx=new TransactionTemplate(transactions); this.storage=storage; this.json=json; this.maxBytes=maxBytes;
        Arrays.setAll(locks,i -> new ReentrantLock());
    }
    public long maxBytes() { return maxBytes; }
    private static ResponseStatusException error(HttpStatus status,String reason) { return new ResponseStatusException(status,reason); }
    private Map<String,Object> one(String sql,Object... args) {
        var rows=db.queryForList(sql,args);
        if(rows.isEmpty()) throw error(HttpStatus.NOT_FOUND,"场景、草稿或文件不存在");
        return rows.get(0);
    }
    private void scene(UUID id,boolean lock) {
        one("select id from ar_scene where id=? and deleted_at is null"+(lock?" for update":""),id);
    }
    public Map<String,Object> detail(UUID id) { return one("select "+DRAFT_COLUMNS+" from ar_draft where id=?",id); }
    private UUID sceneOf(UUID id) { return UUID.fromString((String)detail(id).get("sceneId")); }
    private void writable(UUID id) { scene(sceneOf(id),true); }
    private void audit(UUID sceneId,UUID draftId,UUID fileId,String action,long actor,String actorName,Map<String,Object> values) {
        var detail=new LinkedHashMap<String,Object>(values);
        detail.put("draftId",draftId.toString());
        if(fileId!=null) detail.put("fileId",fileId.toString());
        try {
            db.update("insert into ar_audit(scene_id,actor_id,actor_name,action,detail) values(?,?,?,?,?::jsonb)",
                sceneId,actor,actorName,action,json.writeValueAsString(detail));
        } catch(JsonProcessingException e) { throw new IllegalStateException(e); }
    }
    private void audit(UUID draftId,UUID fileId,String action,Map<String,Object> values) {
        audit(sceneOf(draftId),draftId,fileId,action,SecurityUtils.getUserId(),SecurityUtils.getUsername(),values);
    }
    public Map<String,Object> list(UUID sceneId,int limit,int offset) {
        scene(sceneId,false);
        return Map.of("items",db.queryForList("select "+DRAFT_COLUMNS+" from ar_draft where scene_id=? order by created_at desc,id limit ? offset ?",sceneId,limit,offset),
            "total",db.queryForObject("select count(*) from ar_draft where scene_id=?",Long.class,sceneId));
    }
    public Map<String,Object> create(UUID sceneId,DraftController.DraftInput input) {
        return tx.execute(s -> {
            scene(sceneId,true);
            var existing=db.queryForList("select id from ar_draft where scene_id=? and request_key=?",sceneId,input.requestKey());
            if(!existing.isEmpty()) return detail((UUID)existing.get(0).get("id"));
            UUID id=UUID.randomUUID();
            db.update("insert into ar_draft(id,scene_id,request_key,description,creator_id,creator_name) values(?,?,?,?,?,?)",
                id,sceneId,input.requestKey(),input.description(),SecurityUtils.getUserId(),SecurityUtils.getUsername());
            audit(id,null,"DRAFT_CREATE",Map.of("description",input.description()));
            return detail(id);
        });
    }
    public Map<String,Object> edit(UUID id,DraftController.EditInput input) {
        return tx.execute(s -> {
            writable(id);
            var before=detail(id);
            if(db.update("update ar_draft set description=?,lock_version=lock_version+1,updated_at=now() where id=? and lock_version=?",
                    input.description(),id,input.expectedVersion())!=1) throw error(HttpStatus.CONFLICT,"草稿已修改，请刷新后重试");
            audit(id,null,"DRAFT_EDIT",Map.of("before",before.get("description"),"after",input.description()));
            return detail(id);
        });
    }
    public void removeDraft(UUID draftId) {
        if(db.queryForList("select id from ar_draft where id=?",draftId).isEmpty()) return;
        writable(draftId);
        UUID sceneId=sceneOf(draftId);
        var draft=detail(draftId);
        var files=db.queryForList("select id from ar_draft_file where draft_id=? order by id",draftId);
        List<ReentrantLock> held=new ArrayList<>();
        try {
            for(var row:files) {
                ReentrantLock guard=lock((UUID)row.get("id"));
                if(!guard.tryLock()) throw error(HttpStatus.CONFLICT,"文件正在上传或校验，暂不能删除草稿");
                held.add(guard);
            }
            var current=db.queryForList("select id,status from ar_draft_file where draft_id=?",draftId);
            if(current.size()!=files.size() || current.stream().anyMatch(row -> "UPLOADING".equals(row.get("status"))))
                throw error(HttpStatus.CONFLICT,"文件正在处理，请稍后刷新再删除草稿");
            audit(sceneId,draftId,null,"DRAFT_DELETE_REQUEST",SecurityUtils.getUserId(),SecurityUtils.getUsername(),
                Map.of("fileCount",files.size(),"description",draft.get("description")));
            for(var row:files) remove(draftId,(UUID)row.get("id"));
            tx.executeWithoutResult(s -> {
                writable(draftId);
                if(db.queryForList("select id from ar_draft where id=? for update",draftId).isEmpty()) return;
                if(db.queryForObject("select count(*) from ar_draft_file where draft_id=?",Long.class,draftId)!=0)
                    throw error(HttpStatus.SERVICE_UNAVAILABLE,"草稿中部分文件未能物理删除，请查看失败原因后重试删除草稿");
                audit(sceneId,draftId,null,"DRAFT_DELETE",SecurityUtils.getUserId(),SecurityUtils.getUsername(),
                    Map.of("physicalFilesDeleted",true,"fileCount",files.size(),"description",draft.get("description")));
                db.update("delete from ar_draft where id=?",draftId);
            });
        } finally {
            for(int i=held.size()-1;i>=0;i--) held.get(i).unlock();
        }
    }
    public Map<String,Object> files(UUID id,int limit,int offset) {
        detail(id);
        return Map.of("items",db.queryForList("select "+FILE_COLUMNS+" from ar_draft_file where draft_id=? and removed_at is null order by created_at,id limit ? offset ?",id,limit,offset),
            "total",db.queryForObject("select count(*) from ar_draft_file where draft_id=? and removed_at is null",Long.class,id));
    }
    private Map<String,Object> file(UUID draftId,UUID id) { return one("select "+FILE_COLUMNS+" from ar_draft_file where draft_id=? and id=? and removed_at is null and not exists(select 1 from ar_file_deletion d where d.file_id=ar_draft_file.id)",draftId,id); }
    public Map<String,Object> register(UUID draftId,DraftController.FileInput input) {
        if(input.bytes()>maxBytes) throw error(HttpStatus.PAYLOAD_TOO_LARGE,"文件超过配置的大小上限");
        if(input.fileName().chars().anyMatch(c -> c<32 || c==127) || input.fileName().contains("/") || input.fileName().contains("\\"))
            throw error(HttpStatus.BAD_REQUEST,"文件名不能包含路径或控制字符");
        if(input.fileName().toLowerCase(Locale.ROOT).endsWith(".aar") && !"CLIENT_LIBRARY".equals(input.kind()))
            throw error(HttpStatus.BAD_REQUEST,"AAR 必须登记为客户端集成库");
        return tx.execute(s -> {
            writable(draftId);
            if(Boolean.TRUE.equals(db.queryForObject("select exists(select 1 from ar_file_deletion where draft_id=? and request_key=?)",Boolean.class,draftId,input.requestKey())))
                throw error(HttpStatus.GONE,"该文件已删除或正在删除，重新添加请使用新的请求标识");
            var rows=db.queryForList("select id,removed_at from ar_draft_file where draft_id=? and request_key=?",draftId,input.requestKey());
            if(!rows.isEmpty()) {
                if(rows.get(0).get("removed_at")!=null) throw error(HttpStatus.GONE,"该文件登记已移除，重新添加请使用新的请求标识");
                var existing=file(draftId,(UUID)rows.get(0).get("id"));
                if(!input.fileName().equals(existing.get("fileName")) || !input.kind().equals(existing.get("kind"))
                    || input.bytes().longValue()!=((Number)existing.get("bytes")).longValue() || !input.sha256().equals(existing.get("sha256")))
                    throw error(HttpStatus.CONFLICT,"同一请求标识已用于不同文件，请刷新核对");
                return existing;
            }
            UUID id=UUID.randomUUID();
            long actor=SecurityUtils.getUserId(); String name=SecurityUtils.getUsername();
            db.update("insert into ar_draft_file(id,draft_id,request_key,file_name,kind,expected_bytes,expected_sha256,storage_key,creator_id,creator_name,last_actor_id,last_actor_name) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                id,draftId,input.requestKey(),input.fileName(),input.kind(),input.bytes(),input.sha256(),id+".bin",actor,name,actor,name);
            audit(draftId,id,"FILE_REGISTER",Map.of("fileName",input.fileName(),"bytes",input.bytes(),"sha256",input.sha256(),"kind",input.kind()));
            return file(draftId,id);
        });
    }
    public void remove(UUID draftId,UUID id) {
        ReentrantLock guard=lock(id);
        if(!guard.tryLock()) throw error(HttpStatus.CONFLICT,"文件正在上传或校验，暂不能删除");
        try {
            boolean completed=Boolean.TRUE.equals(tx.execute(s -> {
                writable(draftId);
                var receipts=db.queryForList("select completed_at from ar_file_deletion where file_id=? and draft_id=?",id,draftId);
                if(!receipts.isEmpty()) {
                    if(receipts.get(0).get("completed_at")!=null) return true;
                    db.update("update ar_file_deletion set failure_reason=null,actor_id=?,actor_name=? where file_id=?",SecurityUtils.getUserId(),SecurityUtils.getUsername(),id);
                    audit(draftId,id,"FILE_DELETE_RETRY",Map.of());
                    return false;
                }
                var row=one("select file_name,status,request_key,expected_bytes,expected_sha256 from ar_draft_file where draft_id=? and id=? for update",draftId,id);
                if("UPLOADING".equals(row.get("status"))) throw error(HttpStatus.CONFLICT,"文件正在处理，请稍后刷新再删除");
                db.update("insert into ar_file_deletion(file_id,draft_id,request_key,actor_id,actor_name) values(?,?,?,?,?)",
                    id,draftId,row.get("request_key"),SecurityUtils.getUserId(),SecurityUtils.getUsername());
                audit(draftId,id,"FILE_DELETE_REQUEST",Map.of("fileName",row.get("file_name"),"previousStatus",row.get("status"),
                    "bytes",row.get("expected_bytes"),"sha256",row.get("expected_sha256")));
                return false;
            }));
            if(!completed && !completeDeletion(draftId,id,false))
                throw error(HttpStatus.SERVICE_UNAVAILABLE,"物理删除未完成，请查看失败原因并重试删除");
        } finally { guard.unlock(); }
    }
    private boolean completeDeletion(UUID draftId,UUID id,boolean recovery) {
        try {
            storage.delete(id);
        } catch(IOException e) {
            tx.executeWithoutResult(s -> {
                var receipt=one("select actor_id,actor_name from ar_file_deletion where file_id=?",id);
                db.update("update ar_file_deletion set failure_reason=? where file_id=? AND completed_at is null",
                    "存储文件删除失败，请检查存储权限或文件占用后重试删除",id);
                audit(sceneOf(draftId),draftId,id,"FILE_DELETE_FAILED",((Number)receipt.get("actor_id")).longValue(),(String)receipt.get("actor_name"),Map.of("recovery",recovery));
            });
            return false;
        }
        tx.executeWithoutResult(s -> {
            var receipt=one("select actor_id,actor_name,completed_at from ar_file_deletion where file_id=? for update",id);
            if(receipt.get("completed_at")!=null) return;
            db.update("delete from ar_draft_file where id=? and draft_id=?",id,draftId);
            db.update("update ar_file_deletion set completed_at=now(),failure_reason=null where file_id=?",id);
            audit(sceneOf(draftId),draftId,id,"FILE_DELETE",((Number)receipt.get("actor_id")).longValue(),(String)receipt.get("actor_name"),
                Map.of("physicalFileDeleted",true,"recovery",recovery,"performedBy",recovery?"SYSTEM_RECONCILIATION":"ADMIN"));
        });
        return true;
    }
    private void reconcileDeletions() {
        UUID cursor=new UUID(0,0);
        while(true) {
            var rows=db.queryForList("select file_id,draft_id from ar_file_deletion where completed_at is null and file_id>? order by file_id limit 100",cursor);
            if(rows.isEmpty()) return;
            for(var row:rows) {
                UUID id=(UUID)row.get("file_id"); cursor=id;
                ReentrantLock guard=lock(id);guard.lock();
                try { completeDeletion((UUID)row.get("draft_id"),id,true); }
                finally { guard.unlock(); }
            }
        }
    }
    private ArtifactStorage.Descriptor descriptor(Map<String,Object> row) {
        return new ArtifactStorage.Descriptor(UUID.fromString((String)row.get("id")),((Number)row.get("bytes")).longValue(),(String)row.get("sha256"));
    }
    private ReentrantLock lock(UUID id) { return locks[(id.hashCode() & Integer.MAX_VALUE)%locks.length]; }
    public Map<String,Object> upload(UUID draftId,UUID id,InputStream input) {
        ReentrantLock lock=lock(id);
        if(!lock.tryLock()) throw error(HttpStatus.CONFLICT,"文件正在处理，请稍后刷新或重试");
        try {
            var row=tx.execute(s -> {
                writable(draftId);
                var current=file(draftId,id);
                if(!"AVAILABLE".equals(current.get("status"))) {
                    db.update("update ar_draft_file set status='UPLOADING',failure_reason=null,verified_bytes=null,verified_sha256=null,attempts=attempts+1,last_actor_id=?,last_actor_name=?,updated_at=now() where id=?",
                        SecurityUtils.getUserId(),SecurityUtils.getUsername(),id);
                    audit(draftId,id,"FILE_UPLOAD_START",Map.of());
                }
                return current;
            });
            try {
                var expected=descriptor(row);
                if(!"AVAILABLE".equals(row.get("status"))) {
                    storage.stage(expected,input);
                    storage.commit(expected);
                }
                storage.verify(expected);
            } catch(IOException e) {
                String reason=switch(String.valueOf(e.getMessage())) {
                    case "Artifact size mismatch" -> "实际文件大小与登记值不一致，请核对原文件";
                    case "Artifact SHA256 mismatch" -> "实际 SHA256 与登记摘要不一致，请核对原文件";
                    case "Artifact exceeds configured storage limit" -> "文件超过当前存储大小上限";
                    default -> "上传中断或存储不可用，请重新选择原文件重试；持续失败请联系管理员检查存储";
                };
                finish(draftId,id,false,reason,false);
                throw error(HttpStatus.UNPROCESSABLE_ENTITY,"文件校验或存储失败，请查看文件记录并重试");
            }
            if(!"AVAILABLE".equals(row.get("status"))) finish(draftId,id,true,null,false);
            return file(draftId,id);
        } finally { lock.unlock(); }
    }
    private void finish(UUID draftId,UUID id,boolean available,String reason,boolean recovery) {
        tx.executeWithoutResult(s -> {
            var before=file(draftId,id);
            db.update("update ar_draft_file set status=?,verified_bytes=case when ? then expected_bytes else null end,verified_sha256=case when ? then expected_sha256 else null end,failure_reason=?,updated_at=now() where id=?",
                available?"AVAILABLE":"FAILED",available,available,reason,id);
            var values=new LinkedHashMap<String,Object>();
            values.put("status",available?"AVAILABLE":"FAILED"); values.put("recovery",recovery);
            if(reason!=null) values.put("reason",reason);
            if(recovery) {
                values.put("performedBy","SYSTEM_RECONCILIATION");
                audit(sceneOf(draftId),draftId,id,"FILE_RECONCILE",((Number)before.get("lastActorId")).longValue(),(String)before.get("lastActorName"),values);
            } else audit(draftId,id,available?"FILE_AVAILABLE":"FILE_FAILED",values);
        });
    }
    /** Runs after Flyway and before application startup completes. Rechecks available files too. */
    @Override public void afterPropertiesSet() {
        reconcileDeletions();
        // Keyset pagination bounds memory even after many uploads.
        UUID cursor=new UUID(0,0);
        while(true) {
            var rows=db.queryForList("select "+FILE_COLUMNS+" from ar_draft_file where id>? and removed_at is null and not exists(select 1 from ar_file_deletion d where d.file_id=ar_draft_file.id) order by id limit 100",cursor);
            if(rows.isEmpty()) break;
            for(var row:rows) {
                UUID id=UUID.fromString((String)row.get("id")); cursor=id;
                UUID draftId=UUID.fromString((String)row.get("draftId"));
                ReentrantLock lock=lock(id); lock.lock();
                try {
                    try {
                        // commit recovers a verified .ready or a committed file missing its DB acknowledgement.
                        storage.commit(descriptor(row));
                        storage.verify(descriptor(row));
                        if(!"AVAILABLE".equals(row.get("status"))) finish(draftId,id,true,null,true);
                    } catch(IOException e) {
                        if(!"FAILED".equals(row.get("status"))) finish(draftId,id,false,"重启对账未找到完整且校验通过的正式文件，请重新上传",true);
                    }
                } finally { lock.unlock(); }
            }
        }
    }
}
