<template>
  <el-drawer :model-value="!!sceneId" title="内容版本草稿" size="90%" :close-on-click-modal="false" :before-close="close">
    <p>文件仅供管理员入库管理。已发布版本文件冻结，仅可修改说明；未发布草稿不能供客户端加载。AAR 请登记为客户端集成库。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section class="published-card" :class="{empty:!published}">
      <div class="published-head">
        <h3>当前发布版本</h3>
        <el-tag v-if="published" type="success">已发布</el-tag>
      </div>
      <template v-if="published">
        <p><span class="meta-label">版本说明</span>{{published.description || '（无说明）'}}</p>
        <p><span class="meta-label">草稿编号</span>{{published.id}}</p>
        <p><span class="meta-label">发布人</span>{{published.publishedByName}}</p>
        <p><span class="meta-label">发布时间</span>{{formatTime(published.publishedAt)}}</p>
        <p class="published-note">已发布版本文件已冻结，仅可修改说明</p>
        <el-button link type="primary" :disabled="busy || removing" @click="selectDraft(published.id)">查看文件</el-button>
      </template>
      <p v-else class="published-empty">该场景尚未发布</p>
    </section>
    <el-form inline @submit.prevent="createDraft">
      <el-form-item label="新草稿说明"><el-input v-model="description" maxlength="2000" placeholder="填写版本说明（可留空）" :disabled="busy || removing" style="width:280px" /></el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="creating" :disabled="busy || removing" @click="createDraft">创建草稿</el-button>
        <el-button :disabled="busy || removing" @click="refresh">刷新</el-button>
      </el-form-item>
    </el-form>
    <el-table :data="drafts" highlight-current-row :current-row-key="selected?.id" row-key="id">
      <el-table-column prop="description" label="版本说明" show-overflow-tooltip />
      <el-table-column prop="id" label="草稿编号" min-width="280" />
      <el-table-column prop="creatorName" label="创建人" width="120" />
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="row.published?'success':'info'">{{row.published?'已发布':'草稿'}}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="260"><template #default="{row}">
        <el-button link type="primary" :disabled="busy || removing" @click="selectDraft(row.id)">查看文件</el-button>
        <el-button v-if="row.published" link disabled>当前发布</el-button>
        <el-button v-else link type="primary" :disabled="busy || removing || publishing" @click="publishDraft(row)">{{published?'替换发布':'发布'}}</el-button>
        <el-button link type="danger" :disabled="busy || removing || row.published" @click="removeDraft(row)">删除</el-button>
      </template></el-table-column>
    </el-table>
    <pagination v-show="draftTotal>20" :total="draftTotal" v-model:page="draftPage" :limit="20" @pagination="loadDrafts" />
    <section v-if="selected" class="draft-files">
      <h3>{{selected.published?'发布文件':'草稿文件'}} · {{selected.id}}</h3>
      <el-alert v-if="selected.published" title="当前为发布版本，文件已冻结，仅可修改说明" type="info" :closable="false" />
      <el-form inline @submit.prevent="saveDescription">
        <el-form-item label="版本说明"><el-input v-model="editDescription" maxlength="2000" :disabled="busy || removing" style="width:280px" /></el-form-item>
        <el-form-item>
          <el-button type="primary" :disabled="busy || removing" :loading="saving" @click="saveDescription">保存说明</el-button>
        </el-form-item>
      </el-form>
      <div v-if="!selected.published" class="upload-bar">
        <el-select v-model="kind" :disabled="busy || removing" aria-label="文件类型" style="width:180px"><el-option label="资源文件" value="RESOURCE_FILE" /><el-option label="客户端集成库" value="CLIENT_LIBRARY" /></el-select>
        <el-button type="primary" :disabled="busy || removing" @click="choose()">选择文件并上传</el-button>
        <input ref="picker" type="file" multiple hidden @change="picked" />
        <span>单文件上限 {{size(maxBytes)}}。中断后重新选择原文件即可重试。</span>
        <el-button v-if="busy" type="warning" @click="cancel">取消本次上传</el-button>
      </div>
      <p role="status">{{progressText}}</p>
      <el-progress v-if="busy" :percentage="progress" />
      <el-table :data="files" v-loading="loadingFiles">
        <el-table-column prop="fileName" label="文件名" min-width="150" show-overflow-tooltip />
        <el-table-column label="类型" width="130"><template #default="{row}">{{row.kind==='CLIENT_LIBRARY'?'客户端集成库':'资源文件'}}</template></el-table-column>
        <el-table-column label="大小" width="130"><template #default="{row}">{{size(row.bytes)}}<br />{{row.bytes}} 字节</template></el-table-column>
        <el-table-column prop="sha256" label="SHA256" min-width="260"><template #default="{row}"><code class="digest">{{row.sha256}}</code></template></el-table-column>
        <el-table-column label="处理状态" width="120"><template #default="{row}"><el-tag :type="row.status==='AVAILABLE'?'success':['FAILED','DELETE_FAILED'].includes(row.status)?'danger':'warning'">{{states[row.status]}}</el-tag></template></el-table-column>
        <el-table-column prop="failureReason" label="失败原因" min-width="200" />
        <el-table-column prop="creatorName" label="创建人" width="110" />
        <el-table-column label="操作" width="190"><template #default="{row}"><el-button v-if="!selected.published && ['PENDING','FAILED'].includes(row.status)" link type="primary" :disabled="busy || removing" @click="choose(row)">重新选择原文件</el-button><el-button v-if="!selected.published" link type="danger" :disabled="busy || removing || ['UPLOADING','DELETING'].includes(row.status)" @click="removeFile(row)">{{row.status==='DELETE_FAILED'?'重试删除':'删除'}}</el-button></template></el-table-column>
      </el-table>
      <pagination v-show="fileTotal>20" :total="fileTotal" v-model:page="filePage" :limit="20" @pagination="loadFiles" />
    </section>
  </el-drawer>
</template>
<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sha256 } from 'js-sha256'
import request from '@/utils/request'
const props=defineProps({sceneId:String})
const emit=defineEmits(['close','sceneUpdated'])
const route=useRoute(),router=useRouter()
const drafts=ref([]),draftTotal=ref(0),draftPage=ref(1),description=ref(''),selected=ref(null),editDescription=ref('')
const files=ref([]),fileTotal=ref(0),filePage=ref(1),maxBytes=ref(0),kind=ref('RESOURCE_FILE'),picker=ref(null)
const busy=ref(false),creating=ref(false),saving=ref(false),loadingFiles=ref(false),error=ref(''),progress=ref(0),progressText=ref('')
const removing=ref(false),publishing=ref(false),published=ref(null),sceneLockVersion=ref(0)
const states={PENDING:'待上传',UPLOADING:'处理中',AVAILABLE:'已校验入库',FAILED:'失败',DELETING:'正在删除',DELETE_FAILED:'删除失败'}
let worker,controller,retryRow,cancelled=false,createKey=null,poll
let draftRequest=0,fileRequest=0,selectionRequest=0
function key(text){const h=sha256(text);return `${h.slice(0,8)}-${h.slice(8,12)}-4${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20,32)}`}
function randomKey(){const bytes=new Uint32Array(4);crypto.getRandomValues(bytes);return key(Array.from(bytes).join('-'))}
function size(n){return n>=1048576?`${(n/1048576).toFixed(1)} MiB`:`${n??0} B`}
function message(e){return e.response?.data?.message||e.message||'请求失败，请刷新核对后重试'}
function formatTime(value){
  if(!value) return ''
  const d=new Date(value)
  if(Number.isNaN(d.getTime())) return value
  const p=n=>String(n).padStart(2,'0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
async function loadDrafts(){
  const sequence=++draftRequest,sceneId=props.sceneId
  const r=await request.get(`/api/v1/scenes/${sceneId}/drafts`,{params:{limit:20,offset:(draftPage.value-1)*20}})
  if(sequence!==draftRequest||sceneId!==props.sceneId)return
  drafts.value=r.items;draftTotal.value=r.total;sceneLockVersion.value=r.sceneLockVersion;published.value=r.published
}
async function loadFiles(){
  if(!selected.value)return
  const sequence=++fileRequest,draftId=selected.value.id
  loadingFiles.value=true
  try{
    const r=await request.get(`/api/v1/drafts/${draftId}/files`,{params:{limit:20,offset:(filePage.value-1)*20}})
    if(sequence!==fileRequest||draftId!==selected.value?.id)return
    files.value=r.items;fileTotal.value=r.total
  }finally{if(sequence===fileRequest)loadingFiles.value=false}
}
async function selectDraft(id){
  const sequence=++selectionRequest,sceneId=props.sceneId
  ++fileRequest;selected.value=null;files.value=[];fileTotal.value=0;loadingFiles.value=false
  try{
    const draft=await request.get(`/api/v1/drafts/${id}`)
    if(sequence!==selectionRequest||sceneId!==props.sceneId)return
    if(draft.sceneId!==sceneId)throw new Error('该草稿不属于当前场景，请重新选择')
    selected.value=draft;editDescription.value=draft.description;filePage.value=1
    await router.replace({query:{...route.query,draftScene:sceneId,draftId:id}})
    if(sequence===selectionRequest)await loadFiles()
  }catch(e){if(sequence===selectionRequest&&sceneId===props.sceneId)error.value=message(e)}
}
async function refresh(){
  try{
    error.value=''
    await loadDrafts()
    if(!selected.value)return
    const sequence=++selectionRequest,sceneId=props.sceneId,id=selected.value.id
    const draft=await request.get(`/api/v1/drafts/${id}`)
    if(sequence!==selectionRequest||sceneId!==props.sceneId)return
    if(draft.sceneId!==sceneId)throw new Error('该草稿不属于当前场景，请重新选择')
    selected.value=draft;editDescription.value=draft.description
    await loadFiles()
  }catch(e){error.value=message(e)}
}
async function createDraft(){creating.value=true;createKey ||= randomKey();try{const r=await request.post(`/api/v1/scenes/${props.sceneId}/drafts`,{requestKey:createKey,description:description.value});createKey=null;description.value='';draftPage.value=1;await loadDrafts();await selectDraft(r.id)}catch(e){error.value=message(e)}finally{creating.value=false}}
async function saveDescription(){saving.value=true;try{selected.value=await request.put(`/api/v1/drafts/${selected.value.id}`,{description:editDescription.value,expectedVersion:selected.value.lockVersion});await loadDrafts();ElMessage.success('说明已保存')}catch(e){error.value=message(e);if(e.response?.status===409)await selectDraft(selected.value.id)}finally{saving.value=false}}
function uploadKey(file,hash,fileKind){
  const stable=key([selected.value.id,file.name,file.size,hash,fileKind].join('|'))
  return sessionStorage.getItem('draft-file-key:'+stable)||stable
}
async function publishDraft(row){
  publishing.value=true
  try{
    const label=row.description?.trim()||row.id
    const current=published.value
    await ElMessageBox.confirm(
      current
        ? `当前发布版本是「${current.description?.trim()||current.id}」。确认将草稿「${label}」替换为该场景的唯一发布版本吗？原发布版本会回到草稿，可再次发布。新发布版本的文件将冻结，仅可修改说明。`
        : `确认将草稿「${label}」发布为该场景的唯一发布版本吗？发布后文件冻结，仅可修改说明。`,
      current?'替换发布版本':'发布版本',
      {confirmButtonText:current?'确认替换':'确认发布',cancelButtonText:'取消',type:'warning',closeOnClickModal:false})
    await request.post(`/api/v1/drafts/${row.id}/publish`,{expectedSceneVersion:sceneLockVersion.value})
    await loadDrafts()
    if(selected.value) await selectDraft(selected.value.id)
    emit('sceneUpdated')
    ElMessage.success(current?'已替换发布版本':'已发布')
  }catch(e){if(e!=='cancel'&&e!=='close'){error.value=message(e);if(e.response?.status===409)await loadDrafts()}}
  finally{publishing.value=false}
}
async function removeDraft(row){
  removing.value=true
  try{
    const label=row.description?.trim()||row.id
    await ElMessageBox.confirm(`确认永久删除草稿“${label}”吗？将删除该草稿及其全部实际文件，无法恢复。操作审计会保留。`,'永久删除草稿',{confirmButtonText:'永久删除',cancelButtonText:'取消',type:'warning',closeOnClickModal:false})
    await request.delete(`/api/v1/drafts/${row.id}`)
    if(selected.value?.id===row.id){
      selected.value=null;files.value=[];fileTotal.value=0
      const query={...route.query};delete query.draftId
      await router.replace({query})
    }
    if(drafts.value.length===1&&draftPage.value>1)draftPage.value--
    await loadDrafts();ElMessage.success('草稿已永久删除')
  }catch(e){if(e!=='cancel'&&e!=='close'){error.value=message(e);await loadDrafts();if(selected.value)await loadFiles()}}
  finally{removing.value=false}
}
async function removeFile(row){
  const draftId=selected.value.id
  removing.value=true
  try{
    await ElMessageBox.confirm(`确认永久删除“${row.fileName}”吗？将删除实际文件及草稿文件记录，无法恢复。操作审计会保留。`,'永久删除草稿文件',{confirmButtonText:'永久删除',cancelButtonText:'取消',type:'warning',closeOnClickModal:false})
    await request.delete(`/api/v1/drafts/${draftId}/files/${row.id}`)
    const stable=key([draftId,row.fileName,row.bytes,row.sha256,row.kind].join('|'))
    sessionStorage.setItem('draft-file-key:'+stable,randomKey())
    if(files.value.length===1&&filePage.value>1)filePage.value--
    await loadFiles();ElMessage.success('文件已永久删除')
  }catch(e){if(e!=='cancel'&&e!=='close'){error.value=message(e);await loadFiles()}}
  finally{removing.value=false}
}
function choose(row){retryRow=row||null;picker.value.multiple=!row;picker.value.value='';picker.value.click()}
let rejectHash
function digest(file){return new Promise((resolve,reject)=>{rejectHash=reject;worker=new Worker(new URL('./hash.worker.js',import.meta.url),{type:'module'});worker.onmessage=({data})=>{if(data.error){worker.terminate();reject(new Error(data.error))}else if(data.digest){worker.terminate();resolve(data.digest)}else{progress.value=data.progress}};worker.onerror=()=>reject(new Error('摘要计算失败'));worker.postMessage(file)})}
function cancel(){cancelled=true;worker?.terminate();rejectHash?.(new Error('已取消；重新选择原文件可重试'));controller?.abort()}
async function picked(event){
  const inputs=Array.from(event.target.files||[]);if(!inputs.length||!selected.value)return
  busy.value=true;cancelled=false;error.value=''
  const draftId=selected.value.id,target=retryRow
  try{
    for(const file of inputs){
      if(cancelled)break
      if(file.size>maxBytes.value)throw new Error(`${file.name} 超过文件大小上限`)
      progress.value=0;progressText.value=`正在计算 ${file.name} 的 SHA256`
      const hash=await digest(file);if(cancelled)break
      let record
      if(target){
        if(file.name!==target.fileName||file.size!==target.bytes||hash!==target.sha256)throw new Error('所选文件与原记录的文件名、大小或摘要不一致')
        record=target
      }else{
        const fileKind=file.name.toLowerCase().endsWith('.aar')?'CLIENT_LIBRARY':kind.value
        try{record=await request.post(`/api/v1/drafts/${draftId}/files`,{requestKey:uploadKey(file,hash,fileKind),fileName:file.name,kind:fileKind,bytes:file.size,sha256:hash})}
        catch(e){if(e.response?.status===410){sessionStorage.setItem('draft-file-key:'+key([draftId,file.name,file.size,hash,fileKind].join('|')),randomKey());throw new Error('该文件原记录已删除，请再次选择文件以重新添加')}throw e}
      }
      if(cancelled)break
      controller=new AbortController();progress.value=0;progressText.value=`正在上传 ${file.name}`
      poll=setInterval(()=>loadFiles().catch(()=>{}),2000)
      const result=await request.put(`/api/v1/drafts/${draftId}/files/${record.id}/content`,file,{headers:{'Content-Type':'application/octet-stream'},timeout:0,signal:controller.signal,onUploadProgress:e=>{progress.value=Math.min(100,Math.round(e.loaded/file.size*100)||0);if(e.loaded>=file.size)progressText.value='传输完成，等待服务端校验和入库确认'}})
      clearInterval(poll)
      if(result.status!=='AVAILABLE')throw new Error('服务端尚未确认文件已校验入库，请刷新核对')
      progressText.value=`${file.name} 已校验入库`;await loadFiles()
    }
  }catch(e){error.value=cancelled?'上传已取消；刷新核对处理状态后，可重新选择原文件重试':message(e);progressText.value='本次操作未确认成功'}
  finally{clearInterval(poll);worker?.terminate();rejectHash=null;controller=null;busy.value=false;await loadFiles().catch(e=>{error.value=message(e)})}
}
function close(done){if(busy.value || removing.value){ElMessage.warning('请等待上传结束或先取消上传');return}emit('close');done?.()}
watch(()=>props.sceneId,async id=>{++selectionRequest;++fileRequest;++draftRequest;selected.value=null;files.value=[];drafts.value=[];fileTotal.value=0;draftTotal.value=0;published.value=null;sceneLockVersion.value=0;loadingFiles.value=false;error.value='';draftPage.value=1;if(!id)return;try{maxBytes.value=(await request.get('/api/v1/drafts/config')).maxBytes;if(id!==props.sceneId)return;await loadDrafts();if(id===props.sceneId&&route.query.draftId)await selectDraft(String(route.query.draftId))}catch(e){if(id===props.sceneId)error.value=message(e)}},{immediate:true})
onBeforeUnmount(()=>{cancel();clearInterval(poll)})
</script>
<style scoped>
.draft-files{margin-top:24px}.upload-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:20px}.digest{word-break:break-all}.el-alert{margin-bottom:16px}
.published-card{border:1px solid #e1f3d8;background:#f0f9eb;border-radius:4px;padding:16px 20px;margin:8px 0 20px}
.published-card.empty{border-color:#ebeef5;background:#f5f7fa}
.published-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px}
.published-card h3{margin:0;font-size:16px}
.published-card p{margin:6px 0}
.meta-label{display:inline-block;width:72px;color:#909399}
.published-note,.published-empty{color:#909399}
.published-empty{text-align:center;margin:24px 0}
</style>
