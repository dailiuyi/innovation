<template><div class="app-container"><h2>场景操作记录</h2><el-button @click="load">刷新</el-button><el-table :data="items" v-loading="loading"><el-table-column prop="actorName" label="操作账号"/><el-table-column prop="action" label="动作"/><el-table-column prop="sceneId" label="场景编号" min-width="220"/><el-table-column prop="createdAt" label="时间（UTC）"/><el-table-column label="变更详情"><template #default="{row}"><el-button link type="primary" @click="detail=JSON.stringify(JSON.parse(row.detail),null,2);open=true">查看</el-button></template></el-table-column></el-table><pagination :total="total" v-model:page="page" v-model:limit="limit" @pagination="load"/><el-dialog v-model="open" title="变更详情"><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{detail}}</pre></el-dialog></div></template>
<script setup>
import request from '@/utils/request'
const items=ref([]),total=ref(0),page=ref(1),limit=ref(20),loading=ref(false),detail=ref(''),open=ref(false)
async function load(){loading.value=true;try{const r=await request.get('/api/v1/audits',{params:{limit:limit.value,offset:(page.value-1)*limit.value}});items.value=r.items;total.value=r.total}finally{loading.value=false}}
load()
</script>
