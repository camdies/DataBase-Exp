<template>
  <div class="account-area" :class="{'account-compact':compact}">
    <el-popover v-if="compact" placement="right-end" trigger="click" :width="224" popper-class="account-popover">
      <template #reference><button type="button" class="account-avatar" aria-label="账户菜单"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-3a7 7 0 0 1 14 0v3"/></svg></button></template>
      <div class="account-popover-content"><span class="account-role">{{roleLabel}}</span><strong>{{auth.username}}</strong><el-button type="danger" plain @click="auth.logout">退出账号</el-button></div>
    </el-popover>
    <div v-else class="account-capsule"><span class="account-avatar" aria-hidden="true"><svg class="ui-icon" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-3a7 7 0 0 1 14 0v3"/></svg></span><div class="account-identity"><span class="account-role">{{roleLabel}}</span><strong :title="auth.username">{{auth.username}}</strong></div><el-tooltip content="退出账号" placement="top"><button class="account-logout" type="button" aria-label="退出账号" @click="auth.logout"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 4H4v16h6M10 12h11m-4-4 4 4-4 4"/></svg></button></el-tooltip></div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { ElPopover, ElTooltip } from 'element-plus'
import { useAuth } from '../auth'
defineProps({compact:Boolean})
const auth=useAuth(),roleLabel=computed(()=>auth.role==='admin'?'管理员':'业务员')
</script>
