<template>
  <el-drawer :model-value="!!sceneId" :title="sceneName?'内容版本草稿 · '+sceneName:'内容版本草稿'" size="90%" :close-on-click-modal="false" :before-close="close">
    <p>所属场景：{{sceneName||sceneId||''}}<span v-if="sceneName">（编号 {{sceneId}}）</span></p>
    <p>文件仅供管理员入库管理。已发布版本文件冻结，仅可修改说明；未发布草稿不能供客户端加载。AAR 请登记为客户端集成库。选择文件夹会在确认后替换当前草稿的全部文件。</p>
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
        <el-button v-else link type="primary" :disabled="busy || removing || publishing || replacing" @click="publishDraft(row)">{{published?'替换发布':'发布'}}</el-button>
        <el-button link type="danger" :disabled="busy || removing || row.published" @click="removeDraft(row)">删除</el-button>
      </template></el-table-column>
    </el-table>
    <pagination v-show="draftTotal>20" :total="draftTotal" v-model:page="draftPage" :limit="20" @pagination="loadDrafts" />
    <section v-if="selected" class="draft-files">
      <h3>当前查看：{{selected.published?'发布文件':'草稿文件'}} · {{selected.id}}</h3>
      <el-alert v-if="selected.published" title="当前为发布版本，文件已冻结，仅可修改说明" type="info" :closable="false" />
      <el-alert v-if="selected.downloadBlockedReason" :title="selected.downloadBlockedReason" type="warning" :closable="false" />
      <el-alert v-if="replacing" title="正在替换全部文件。新目录完整上传并校验成功后才会永久替换原文件；失败可重试或取消。替换期间不能发布、下载或增删原文件。" type="warning" :closable="false" />
      <el-form inline @submit.prevent="saveDescription">
        <el-form-item label="版本说明"><el-input v-model="editDescription" maxlength="2000" :disabled="busy || removing" style="width:280px" /></el-form-item>
        <el-form-item>
          <el-button type="primary" :disabled="busy || removing" :loading="saving" @click="saveDescription">保存说明</el-button>
        </el-form-item>
      </el-form>
      <div v-if="!selected.published" class="upload-bar">
        <el-select v-model="kind" :disabled="busy || removing || replacing" aria-label="文件类型" style="width:180px"><el-option label="资源文件" value="RESOURCE_FILE" /><el-option label="客户端集成库" value="CLIENT_LIBRARY" /></el-select>
        <el-button type="primary" :disabled="busy || removing || replacing" @click="choose()">选择文件并上传</el-button>
        <el-button type="primary" :disabled="busy || removing" @click="chooseFolder">选择文件夹并上传</el-button>
        <input id="draft-file-picker" ref="picker" type="file" multiple hidden @change="picked" />
        <input id="draft-folder-picker" ref="folderPicker" type="file" webkitdirectory directory multiple hidden @change="pickedFolder" />
        <span>单文件上限 {{size(maxBytes)}}，集合上限 {{collectionMaxFiles}} 个 / {{size(collectionMaxBytes)}}。文件夹入口会替换全部文件。中断后可重试。</span>
        <el-button v-if="busy" type="warning" @click="cancel">取消本次上传</el-button>
        <el-button v-if="replacing && !busy" type="warning" :disabled="removing" @click="cancelReplacement">取消替换</el-button>
      </div>
      <div class="upload-bar">
        <el-button :disabled="busy || removing || replacing || !!selected.downloadBlockedReason" :loading="zipPreparing" @click="downloadZip">下载 ZIP</el-button>
        <el-button :disabled="busy || removing || replacing || !!selected.downloadBlockedReason" @click="showManifest">查看下载清单</el-button>
        <span v-if="zipPreparing">正在准备 ZIP，首次准备需要等待打包完成。</span>
      </div>
      <p v-if="replacing" role="status">替换进度 {{replacement.availableCount||0}} / {{replacement.fileCount||0}}，失败 {{replacement.failedCount||0}}，共 {{size(replacement.totalBytes)}}。</p>
      <p role="status">{{progressText}}</p>
      <el-progress v-if="busy" :percentage="progress" />
      <el-table :data="files" v-loading="loadingFiles">
        <el-table-column prop="relativePath" label="相对路径" min-width="220" show-overflow-tooltip />
        <el-table-column prop="fileName" label="文件名" min-width="120" show-overflow-tooltip />
        <el-table-column label="类型" width="130"><template #default="{row}">{{row.kind==='CLIENT_LIBRARY'?'客户端集成库':'资源文件'}}</template></el-table-column>
        <el-table-column label="大小" width="130"><template #default="{row}">{{size(row.bytes)}}<br />{{row.bytes}} 字节</template></el-table-column>
        <el-table-column prop="sha256" label="SHA256" min-width="260"><template #default="{row}"><code class="digest">{{row.sha256}}</code></template></el-table-column>
        <el-table-column label="处理状态" width="120"><template #default="{row}"><el-tag :type="row.status==='AVAILABLE'?'success':['FAILED','DELETE_FAILED'].includes(row.status)?'danger':'warning'">{{states[row.status]}}</el-tag></template></el-table-column>
        <el-table-column prop="failureReason" label="失败原因" min-width="200" />
        <el-table-column prop="creatorName" label="创建人" width="110" />
        <el-table-column label="操作" width="220"><template #default="{row}">
          <el-button link type="primary" :disabled="busy || removing || replacing || !!selected.downloadBlockedReason" @click="downloadOne(row)">下载</el-button>
          <el-button v-if="!selected.published && ['PENDING','FAILED'].includes(row.status)" link type="primary" :disabled="busy || removing || replacing" @click="choose(row)">重新选择原文件</el-button>
          <el-button v-if="!selected.published" link type="danger" :disabled="busy || removing || replacing || ['UPLOADING','DELETING'].includes(row.status)" @click="removeFile(row)">{{row.status==='DELETE_FAILED'?'重试删除':'删除'}}</el-button>
        </template></el-table-column>
      </el-table>
      <pagination v-show="fileTotal>20" :total="fileTotal" v-model:page="filePage" :limit="20" @pagination="loadFiles" />
    </section>
    <el-dialog v-model="manifestVisible" title="下载清单" width="720px">
      <p v-if="manifest">集合 {{manifest.collectionId}} · {{manifest.fileCount}} 个文件 · {{size(manifest.totalBytes)}}</p>
      <el-table v-if="manifest" :data="manifest.files" max-height="360">
        <el-table-column prop="relativePath" label="相对路径" min-width="220" show-overflow-tooltip />
        <el-table-column label="大小" width="140"><template #default="{row}">{{size(row.bytes)}}</template></el-table-column>
        <el-table-column prop="sha256" label="SHA256" min-width="240"><template #default="{row}"><code class="digest">{{row.sha256}}</code></template></el-table-column>
      </el-table>
    </el-dialog>
  </el-drawer>
</template>
<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sha256 } from 'js-sha256'
import axios from 'axios'
import { saveAs } from 'file-saver'
import { getToken } from '@/utils/auth'
import { blobValidate } from '@/utils/ruoyi'
import request from '@/utils/request'
const props=defineProps({sceneId:String})
const emit=defineEmits(['close','sceneUpdated'])
const route=useRoute(),router=useRouter()
const drafts=ref([]),draftTotal=ref(0),draftPage=ref(1),description=ref(''),selected=ref(null),editDescription=ref('')
const files=ref([]),fileTotal=ref(0),filePage=ref(1),maxBytes=ref(0),collectionMaxFiles=ref(200),collectionMaxBytes=ref(0),kind=ref('RESOURCE_FILE'),picker=ref(null),folderPicker=ref(null)
const busy=ref(false),creating=ref(false),saving=ref(false),loadingFiles=ref(false),error=ref(''),progress=ref(0),progressText=ref('')
const removing=ref(false),publishing=ref(false),published=ref(null),sceneLockVersion=ref(0),sceneName=ref('')
const replacement=ref(null),zipPreparing=ref(false),manifestVisible=ref(false),manifest=ref(null)
const replacing=ref(false)
const states={PENDING:'待上传',UPLOADING:'处理中',AVAILABLE:'已校验入库',FAILED:'失败',DELETING:'正在删除',DELETE_FAILED:'删除失败'}
let worker,controller,retryRow,cancelled=false,createKey=null,poll
let draftRequest=0,fileRequest=0,selectionRequest=0,sceneRequest=0
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
async function loadReplacement(draft){
  replacing.value=false;replacement.value=null
  if(!draft?.pendingReplacement?.id)return
  const sequence=selectionRequest,sceneSequence=sceneRequest
  const result=await request.get(`/api/v1/drafts/${draft.id}/replacements/${draft.pendingReplacement.id}`)
  if(sequence!==selectionRequest||sceneSequence!==sceneRequest)return
  replacement.value=result
  replacing.value=result?.status==='PENDING'
}
async function selectDraft(id){
  const sequence=++selectionRequest,sceneId=props.sceneId
  ++fileRequest;selected.value=null;files.value=[];fileTotal.value=0;loadingFiles.value=false;replacing.value=false;replacement.value=null
  try{
    const draft=await request.get(`/api/v1/drafts/${id}`)
    if(sequence!==selectionRequest||sceneId!==props.sceneId)return
    if(draft.sceneId!==sceneId)throw new Error('该草稿不属于当前场景，请重新选择')
    selected.value=draft;editDescription.value=draft.description;filePage.value=1
    await router.replace({query:{...route.query,draftScene:sceneId,draftId:id}})
    if(sequence===selectionRequest){await loadFiles();if(sequence===selectionRequest)await loadReplacement(draft)}
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
    await loadFiles();await loadReplacement(draft)
  }catch(e){error.value=message(e)}
}
async function createDraft(){creating.value=true;createKey ||= randomKey();try{const r=await request.post(`/api/v1/scenes/${props.sceneId}/drafts`,{requestKey:createKey,description:description.value});createKey=null;description.value='';draftPage.value=1;await loadDrafts();await selectDraft(r.id)}catch(e){error.value=message(e)}finally{creating.value=false}}
async function saveDescription(){saving.value=true;try{selected.value=await request.put(`/api/v1/drafts/${selected.value.id}`,{description:editDescription.value,expectedVersion:selected.value.lockVersion});await loadDrafts();ElMessage.success('说明已保存')}catch(e){error.value=message(e);if(e.response?.status===409)await selectDraft(selected.value.id)}finally{saving.value=false}}
function uploadKey(file,hash,fileKind){
  const stable=key([selected.value.id,file.name,file.size,hash,fileKind].join('|'))
  return sessionStorage.getItem('draft-file-key:'+stable)||stable
}
async function publishDraft(row){
  const sceneSequence=sceneRequest
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
    if(sceneSequence!==sceneRequest)return
    await request.post(`/api/v1/drafts/${row.id}/publish`,{expectedSceneVersion:sceneLockVersion.value})
    if(sceneSequence!==sceneRequest)return
    await loadDrafts()
    if(sceneSequence!==sceneRequest)return
    if(published.value) await selectDraft(published.value.id)
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
      selected.value=null;files.value=[];fileTotal.value=0;replacing.value=false;replacement.value=null
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
    await refresh();ElMessage.success('文件已永久删除')
  }catch(e){if(e!=='cancel'&&e!=='close'){error.value=message(e);await loadFiles()}}
  finally{removing.value=false}
}
function choose(row){retryRow=row||null;picker.value.multiple=!row;picker.value.value='';picker.value.click()}
function chooseFolder(){folderPicker.value.value='';folderPicker.value.click()}
async function cancelReplacement(){
  if(!replacement.value)return
  try{
    await ElMessageBox.confirm('确认取消本次文件夹替换吗？将清理尚未切换的新文件，并继续使用原来的文件集合。','取消替换',{confirmButtonText:'确认取消替换',cancelButtonText:'返回',type:'warning',closeOnClickModal:false})
    await request.post(`/api/v1/drafts/${selected.value.id}/replacements/${replacement.value.id}/cancel`)
    await refresh();ElMessage.success('已取消替换，仍使用原文件')
  }catch(e){if(e!=='cancel'&&e!=='close')error.value=message(e)}
}
let rejectHash
function digest(file){return new Promise((resolve,reject)=>{rejectHash=reject;worker=new Worker(new URL('./hash.worker.js',import.meta.url),{type:'module'});worker.onmessage=({data})=>{if(data.error){worker.terminate();reject(new Error(data.error))}else if(data.digest){worker.terminate();resolve(data.digest)}else{progress.value=data.progress}};worker.onerror=()=>reject(new Error('摘要计算失败'));worker.postMessage(file)})}
function cancel(){cancelled=true;worker?.terminate();rejectHash?.(new Error('已取消；重新选择原文件可重试'));controller?.abort()}
async function uploadContent(draftId,record,file,label){
  controller=new AbortController();progress.value=0;progressText.value=`正在上传 ${label}`
  poll=setInterval(()=>loadFiles().catch(()=>{}),2000)
  const result=await request.put(`/api/v1/drafts/${draftId}/files/${record.id}/content`,file,{headers:{'Content-Type':'application/octet-stream'},timeout:0,signal:controller.signal,onUploadProgress:e=>{progress.value=Math.min(100,Math.round(e.loaded/file.size*100)||0);if(e.loaded>=file.size)progressText.value='传输完成，等待服务端校验和入库确认'}})
  clearInterval(poll)
  if(result.status!=='AVAILABLE')throw new Error('服务端尚未确认文件已校验入库，请刷新核对')
  progressText.value=`${label} 已校验入库`
}
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
      await uploadContent(draftId,record,file,file.name)
      await loadFiles()
    }
  }catch(e){error.value=cancelled?'上传已取消；刷新核对处理状态后，可重新选择原文件重试':message(e);progressText.value='本次操作未确认成功'}
  finally{clearInterval(poll);worker?.terminate();rejectHash=null;controller=null;busy.value=false;await refresh().catch(e=>{error.value=message(e)})}
}
async function pickedFolder(event){
  const inputs=Array.from(event.target.files||[]);if(!inputs.length||!selected.value)return
  if(selected.value.published){error.value='已发布版本文件已冻结，仅可修改说明';return}
  const draftId=selected.value.id
  try{
    if((selected.value.fileCount||fileTotal.value)>0 && !replacing.value){
      await ElMessageBox.confirm('当前草稿已有文件。此次操作会替换当前草稿的全部文件。新目录完整上传并校验成功后才永久替换原文件；失败可重试或取消替换。取消本确认不会开始替换。','替换全部文件',{confirmButtonText:'确认替换全部文件',cancelButtonText:'取消',type:'warning',closeOnClickModal:false})
    }
  }catch{event.target.value='';return}
  busy.value=true;cancelled=false;error.value=''
  try{
    const prepared=[]
    for(const file of inputs){
      if(cancelled)break
      const relative=file.webkitRelativePath||file.name
      if(file.size>maxBytes.value)throw new Error(`${relative} 超过文件大小上限`)
      progress.value=0;progressText.value=`正在计算 ${relative} 的 SHA256`
      const hash=await digest(file);if(cancelled)break
      const fileKind=file.name.toLowerCase().endsWith('.aar')?'CLIENT_LIBRARY':kind.value
      prepared.push({file,relativePath:relative,kind:fileKind,bytes:file.size,sha256:hash,requestKey:key([draftId,relative,file.size,hash,fileKind].join('|'))})
    }
    if(cancelled)throw new Error('已取消')
    if(prepared.length>collectionMaxFiles.value)throw new Error('超过每个文件集合的文件数量上限')
    const total=prepared.reduce((n,item)=>n+item.bytes,0)
    if(total>collectionMaxBytes.value)throw new Error('超过每个文件集合的总大小上限')
    const requestKey=(replacing.value && replacement.value?.status==='PENDING' && replacement.value.requestKey)
      ? replacement.value.requestKey
      : randomKey()
    const batch=await request.post(`/api/v1/drafts/${draftId}/replacements`,{requestKey,files:prepared.map(({file,...meta})=>meta)})
    replacement.value=batch;replacing.value=true
    const byPath=new Map((batch.items||[]).map(item=>[item.relativePath,item]))
    let done=0
    for(const item of prepared){
      if(cancelled)break
      const record=byPath.get(item.relativePath)
      if(!record)throw new Error(`服务端未返回 ${item.relativePath}`)
      if(record.status==='AVAILABLE'){done++;continue}
      progressText.value=`正在上传 ${done+1}/${prepared.length} ${item.relativePath}`
      await uploadContent(draftId,record,item.file,item.relativePath)
      done++
    }
    await refresh()
    if(!cancelled)ElMessage.success(replacing.value?'文件夹已上传，等待全部校验完成后才会替换原文件':'文件夹已替换原文件')
  }catch(e){error.value=cancelled?'上传已取消；可重试同一文件夹或取消替换':message(e);progressText.value='本次操作未确认成功';await refresh().catch(()=>{})}
  finally{clearInterval(poll);worker?.terminate();rejectHash=null;controller=null;busy.value=false;event.target.value=''}
}
function filenameFromDisposition(header,fallback){
  if(!header) return fallback
  const star=/filename\*=UTF-8''([^;]+)/i.exec(header)
  if(star){try{return decodeURIComponent(star[1])}catch{return star[1]}}
  const plain=/filename="?([^";]+)"?/i.exec(header)
  return plain?plain[1]:fallback
}
async function downloadAuthorized(path,fallbackName){
  const res=await axios.get((import.meta.env.VITE_APP_BASE_API||'')+path,{responseType:'blob',timeout:0,headers:{Authorization:'Bearer '+getToken()}})
  if(!blobValidate(res.data)){
    const text=await res.data.text()
    let msg='下载失败'
    try{const parsed=JSON.parse(text);msg=parsed.message||parsed.msg||msg}catch{}
    throw new Error(msg)
  }
  saveAs(new Blob([res.data]),filenameFromDisposition(res.headers['content-disposition'],fallbackName))
}
async function downloadOne(row){
  try{
    const collectionId=selected.value.currentCollectionId
    const generation=selected.value.collectionGeneration
    await downloadAuthorized(`/api/v1/drafts/${selected.value.id}/files/${row.id}/content?collectionId=${collectionId}&generation=${generation}`,row.fileName)
  }catch(e){error.value=message(e)}
}
async function showManifest(){
  try{
    manifest.value=await request.get(`/api/v1/drafts/${selected.value.id}/download-manifest`)
    manifestVisible.value=true
  }catch(e){error.value=message(e)}
}
const zipResultUnconfirmed='请求等待超时，ZIP 构建结果尚未确认，后端可能仍在处理。请稍后重试。'
const zipDownloadFailed='ZIP 下载失败，请重试'
async function downloadZip(){
  zipPreparing.value=true
  error.value=''
  progressText.value='正在准备 ZIP'
  try{
    let exported
    try{
      exported=await request.post(`/api/v1/drafts/${selected.value.id}/zip-exports`,{collectionId:selected.value.currentCollectionId,generation:selected.value.collectionGeneration},{timeout:0})
    }catch(e){
      // A gateway 504, a client timeout or an interrupted connection never proves the build failed.
      const unconfirmed=e?.response?.status===504||(!e?.response&&(e?.isAxiosError||!!e?.request))
      error.value=unconfirmed?zipResultUnconfirmed:message(e)
      progressText.value=unconfirmed?'ZIP 准备结果未确认，可手动重试':'ZIP 准备失败，可手动重试'
      return
    }
    progressText.value='ZIP 已准备好，开始下载'
    try{
      await downloadAuthorized(exported.downloadPath,exported.downloadPath.endsWith('/content')?'draft.zip':'draft.zip')
      progressText.value='ZIP 已开始下载'
    }catch{error.value=zipDownloadFailed;progressText.value='ZIP 已准备好，下载未完成，可手动重试'}
  }finally{zipPreparing.value=false}
}
function close(done){if(busy.value || removing.value){ElMessage.warning('请等待上传结束或先取消上传');return}emit('close');done?.()}
async function loadSceneName(id,sequence){
  try{
    const scene=await request.get(`/api/v1/scenes/${id}`)
    if(sequence!==sceneRequest)return
    sceneName.value=scene?.name||''
  }catch{if(sequence===sceneRequest)sceneName.value=''}
}
watch(()=>props.sceneId,async id=>{
  const sceneSequence=++sceneRequest,selectionSequence=++selectionRequest
  ++fileRequest;++draftRequest
  selected.value=null;files.value=[];drafts.value=[];fileTotal.value=0;draftTotal.value=0
  published.value=null;sceneLockVersion.value=0;loadingFiles.value=false;error.value='';draftPage.value=1
  replacing.value=false;replacement.value=null;manifestVisible.value=false;manifest.value=null;progressText.value=''
  sceneName.value=''
  if(!id)return
  loadSceneName(id,sceneSequence)
  const restoredId=route.query.draftScene===id ? route.query.draftId : null
  try{
    const cfg=await request.get('/api/v1/drafts/config')
    if(sceneSequence!==sceneRequest)return
    maxBytes.value=cfg.maxBytes;collectionMaxFiles.value=cfg.collectionMaxFiles;collectionMaxBytes.value=cfg.collectionMaxBytes
    await loadDrafts()
    if(sceneSequence!==sceneRequest||selectionSequence!==selectionRequest)return
    const initialId=restoredId || published.value?.id
    if(initialId)await selectDraft(String(initialId))
  }catch(e){if(sceneSequence===sceneRequest)error.value=message(e)}
},{immediate:true})
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
