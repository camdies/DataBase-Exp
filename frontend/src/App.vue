<template>
  <el-config-provider :locale="zhCn">
    <div v-if="!auth.token" class="login-shell">
      <section class="login-story" aria-label="系统介绍">
        <span class="story-eyebrow">企业业务系统</span>
        <div class="story-content">
          <h1>订单与库存，<br><em>一处管理</em></h1>
          <p>从下单、扣减库存到发货追踪，每一步都清晰可查，让履约更稳、更快。</p>
          <ul class="story-features">
            <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 8 8-4 8 4-8 4Zm0 4 8 4 8-4M4 16l8 4 8-4"/></svg><div><strong>订单履约一体化</strong><span>下单、发货、取消在同一工作台完成</span></div></li>
            <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 7 8-4 8 4v10l-8 4-8-4Zm0 0 8 5 8-5M12 12v9"/></svg><div><strong>分仓库存实时可见</strong><span>按仓库查询可用数量，及时补充库存</span></div></li>
            <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Zm-4 9 3 3 5-6"/></svg><div><strong>事务保护数据一致</strong><span>库存不足时整笔订单不生效，不会超卖</span></div></li>
          </ul>
        </div>
        <div class="story-flow" aria-hidden="true"><span>客户</span> → <span>订单</span> → <span>订单明细</span> ← <span>商品</span> → <span>分仓库存</span></div>
      </section>
      <div class="login-form-panel">
        <section class="login-card" aria-labelledby="login-title">
          <h2 id="login-title">登录</h2><p class="muted">请使用分配给您的业务账户登录</p>
          <el-form label-position="top" @submit.prevent="login">
            <el-form-item label="用户名"><el-input v-model="form.username" autocomplete="username" placeholder="请输入用户名"><template #prefix><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-3a7 7 0 0 1 14 0v3"/></svg></template></el-input></el-form-item>
            <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" placeholder="请输入密码"><template #prefix><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></svg></template></el-input></el-form-item>
            <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
            <el-button class="login-submit" type="primary" native-type="submit" :loading="busy">进入工作台 <span aria-hidden="true">→</span></el-button>
          </el-form>
          <p class="login-caption">企业订单与库存管理</p>
        </section>
      </div>
    </div>
    <div v-else class="app-shell" :class="{'sidebar-collapsed':sidebarCollapsed}">
      <a class="skip-link" href="#main-content" @click.prevent="focusContent">跳转到业务内容</a>
      <aside class="sidebar">
        <div class="sidebar-control"><button class="sidebar-toggle" :aria-label="sidebarCollapsed?'展开菜单':'收起菜单'" :aria-expanded="!sidebarCollapsed" aria-controls="business-nav" @click="toggleSidebar"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/><path :d="sidebarCollapsed?'m13 9 3 3-3 3':'m16 9-3 3 3 3'"/></svg></button><span class="sidebar-control-label">收起菜单</span><kbd>Ctrl B</kbd></div>

        <nav id="business-nav" aria-label="主导航">
          <template v-for="group in navGroups" :key="group.label"><div class="nav-label">{{group.label}}</div>
          <el-tooltip v-for="entry in group.entries" :key="entry.to" :content="entry.label" placement="right" :disabled="!sidebarCollapsed || narrowScreen" popper-class="sidebar-tooltip">
            <router-link :to="entry.to" :aria-label="entry.label"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="entry.path"/></svg><span class="nav-text">{{entry.label}}</span><span v-if="entry.to==='/orders' && pendingCount>0" class="pending-badge" :aria-label="pendingCount+' 个待发货订单'">{{pendingCount}}</span></router-link>
          </el-tooltip></template>
        </nav>
        <AccountMenu :compact="sidebarCollapsed || narrowScreen"/>
      </aside>
      <div class="main-area">
        <header class="topbar"><div class="breadcrumb"><span>工作台</span><span aria-hidden="true">/</span><strong>{{navigation.find(entry=>entry.to===route.path)?.label||'工作台'}}</strong></div><div class="user-bar"><GlobalSearch/></div></header>
        <main id="main-content" tabindex="-1"><router-view /></main>
      </div>
    </div>
  </el-config-provider>
</template>
<script setup>
import { ElConfigProvider, ElTooltip } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { reactive, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import GlobalSearch from './components/GlobalSearch.vue'
import AccountMenu from './components/AccountMenu.vue'
import { useAuth } from './auth'
import { api } from './api'
const route=useRoute(), auth=useAuth(), form=reactive({username:'',password:''}), busy=ref(false), error=ref('')
const pendingCount=ref(null)
let badgeGeneration=0
async function refreshPending(){const id=++badgeGeneration;pendingCount.value=null;if(!auth.token)return;try{const data=await api.get('/orders',{params:{status:'pending',page:1}});if(id===badgeGeneration)pendingCount.value=data.counts?.pending??null}catch{if(id===badgeGeneration)pendingCount.value=null}}
watch(()=>[auth.token,route.fullPath],refreshPending,{immediate:true})
async function login(){busy.value=true;error.value='';try{await auth.login(form);form.password=''}catch(e){error.value=e.message}finally{busy.value=false}}
function focusContent(){document.getElementById('main-content')?.focus()}
function expired(){auth.logout();error.value='登录已过期，请重新登录'}

const navigation=[
  {to:'/model',label:'模型与代码',path:'M4 4h16v16H4zM4 10h16M10 10v10'},
  {to:'/overview',label:'总览',path:'m3 11 9-8 9 8M5 10v11h14V10M10 21v-7h4v7'},
  {to:'/orders',label:'订单履约',path:'M3 5h11v12H3z M14 9h4l3 4v4h-7 M6 17a2 2 0 1 0 4 0m6 0a2 2 0 1 0 4 0'},
  {to:'/inventory',label:'商品与库存',path:'m12 3 9 5v9l-9 5-9-5V8Zm-9 5 9 5 9-5M12 13v9M7.5 5.5l9 5'},
]
const navGroups=[{label:'业务工作台',entries:navigation.filter(e=>e.to!=='/model')},{label:'数据工程',entries:navigation.filter(e=>e.to==='/model')}]
const sidebarCollapsed=ref(false), narrowScreen=ref(false)
let hasSidebarPreference=false
function readSidebarPreference(){
  try{
    const stored=localStorage.getItem('ui.sidebar.collapsed')
    hasSidebarPreference=stored==='true'||stored==='false'
    sidebarCollapsed.value=hasSidebarPreference?stored==='true':window.innerWidth<1050&&window.innerWidth>720
  }catch{hasSidebarPreference=true;sidebarCollapsed.value=false}
  narrowScreen.value=window.innerWidth<=720
}
function toggleSidebar(){
  if(narrowScreen.value)return
  sidebarCollapsed.value=!sidebarCollapsed.value
  hasSidebarPreference=true
  try{localStorage.setItem('ui.sidebar.collapsed',String(sidebarCollapsed.value))}catch{ /* Keep the in-memory preference when storage is unavailable. */ }
}
function resizeSidebar(){narrowScreen.value=window.innerWidth<=720;if(!hasSidebarPreference)sidebarCollapsed.value=window.innerWidth<1050&&!narrowScreen.value}
function sidebarShortcut(event){
  if(!auth.token||narrowScreen.value||event.repeat||event.altKey||!(event.ctrlKey||event.metaKey)||event.key.toLowerCase()!=='b')return
  if(event.target instanceof Element&&event.target.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="combobox"]'))return
  event.preventDefault();toggleSidebar()
}
onMounted(()=>{readSidebarPreference();window.addEventListener('orders-changed',refreshPending);window.addEventListener('session-expired',expired);window.addEventListener('keydown',sidebarShortcut);window.addEventListener('resize',resizeSidebar)})
onUnmounted(()=>{badgeGeneration++;window.removeEventListener('orders-changed',refreshPending);window.removeEventListener('session-expired',expired);window.removeEventListener('keydown',sidebarShortcut);window.removeEventListener('resize',resizeSidebar)})
</script>

