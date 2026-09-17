<template><div class="app-container"><h2>账号管理</h2><p>所有管理员具有相同权限。禁用、删除或重置密码会使旧登录凭证失效。删除账号后保留历史操作记录。</p>
  <el-form inline><el-form-item label="账号"><el-input v-model="name" clearable /></el-form-item><el-button @click="search">查询</el-button><el-button type="primary" @click="open=true">新增账号</el-button></el-form>
  <el-table :data="items" v-loading="loading"><el-table-column prop="userName" label="账号"/><el-table-column prop="nickName" label="姓名"/><el-table-column label="状态"><template #default="{row}">{{row.status==='0'?'正常':'停用'}}</template></el-table-column>
  <el-table-column label="操作"><template #default="{row}"><template v-if="row.userName!=='bootstrap'"><el-button link type="primary" @click="status(row)">{{row.status==='0'?'禁用':'启用'}}</el-button><el-button link type="primary" @click="reset(row)">重置密码</el-button></template><el-button link type="danger" :disabled="deleting" @click="remove(row)">删除</el-button></template></el-table-column></el-table>
  <pagination :total="total" v-model:page="page" v-model:limit="limit" @pagination="load"/>
  <el-dialog v-model="open" title="新增账号" width="480px"><el-form label-width="90px"><el-form-item label="账号"><el-input v-model="form.userName" maxlength="30"/></el-form-item><el-form-item label="姓名"><el-input v-model="form.nickName" maxlength="30"/></el-form-item><el-form-item label="初始密码"><el-input type="password" v-model="form.password" show-password autocomplete="new-password" placeholder="12–64 个字符"/></el-form-item></el-form><template #footer><el-button @click="open=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">创建</el-button></template></el-dialog>
</div></template>
<script setup>
import request from '@/utils/request'
import {ElMessage,ElMessageBox} from 'element-plus'
const deleting=ref(false)
const items=ref([]),total=ref(0),page=ref(1),limit=ref(20),name=ref(''),loading=ref(false),open=ref(false),saving=ref(false),form=ref({userName:'',nickName:'',password:''})
async function load(){loading.value=true;try{const r=await request.get('/system/user/list',{params:{pageNum:page.value,pageSize:limit.value,userName:name.value}});items.value=r.rows;total.value=r.total}finally{loading.value=false}}
function search(){page.value=1;load()}
async function save(){saving.value=true;try{await request.post('/system/user',form.value);open.value=false;form.value={};ElMessage.success('账号已创建');await load()}finally{saving.value=false}}
async function status(row){try{await ElMessageBox.confirm('确认'+(row.status==='0'?'禁用':'启用')+'该账号？','账号状态');await request.put('/system/user/changeStatus',{userId:row.userId,status:row.status==='0'?'1':'0'});await load()}catch{}}
async function reset(row){try{const {value}=await ElMessageBox.prompt('填写 12–64 个字符的新密码','重置密码',{inputType:'password',inputValidator:v=>v?.length>=12&&v.length<=64||'长度应为 12–64 个字符'});await request.put('/system/user/resetPwd',{userId:row.userId,password:value});ElMessage.success('密码已重置')}catch{}}
async function remove(row){
  if(deleting.value) return
  deleting.value=true
  try{
    await ElMessageBox.confirm(`确认删除账号“${row.userName}”吗？删除后该账号将无法登录，历史操作记录仍会保留。`,'删除账号',{
      confirmButtonText:'确认删除',cancelButtonText:'取消',type:'warning',closeOnClickModal:false,autofocus:false,confirmButtonClass:'el-button--danger'
    })
    await request.delete('/system/user/'+row.userId)
    ElMessage.success('账号已删除')
    if(items.value.length===1 && page.value>1) page.value--
    await load()
  }catch{}finally{deleting.value=false}
}
load()
</script>
