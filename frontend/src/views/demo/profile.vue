<template><div class="app-container"><h2>个人设置</h2><p>修改密码后需要重新登录。</p><el-form style="max-width:480px" label-width="100px"><el-form-item label="当前密码"><el-input type="password" v-model="oldPassword" autocomplete="current-password"/></el-form-item><el-form-item label="新密码"><el-input type="password" v-model="newPassword" autocomplete="new-password" show-password maxlength="64" placeholder="6–64 个字符"/></el-form-item><el-button type="primary" :loading="saving" @click="save">修改密码</el-button></el-form></div></template>
<script setup>
import request from '@/utils/request'
import {removeToken} from '@/utils/auth'
import {ElMessage} from 'element-plus'
const oldPassword=ref(''),newPassword=ref(''),saving=ref(false)
async function save(){saving.value=true;try{await request.put('/system/user/profile/updatePwd',{oldPassword:oldPassword.value,newPassword:newPassword.value});ElMessage.success('密码已修改，请重新登录');removeToken();location.href='/login'}finally{saving.value=false}}
</script>
