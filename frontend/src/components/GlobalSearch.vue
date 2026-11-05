<template>
  <button class="global-search-trigger" type="button" aria-label="全局搜索" @click="open"><span>⌕ 搜索订单号、客户、SKU</span><kbd>Ctrl K</kbd></button>
  <el-dialog v-model="visible" title="全局搜索" class="global-search-dialog" append-to-body width="min(680px, 92vw)" @opened="input?.focus()">
    <form class="global-search-form" @submit.prevent="search"><el-input ref="input" v-model="keyword" maxlength="80" clearable aria-label="全局搜索关键词" placeholder="输入订单号、客户姓名、商品名或 SKU"/><el-button type="primary" native-type="submit" :loading="loading">搜索</el-button></form>
    <div v-loading="loading" class="global-search-results" aria-live="polite">
      <el-alert v-if="error" :title="error" type="error" :closable="false"/>
      <template v-else-if="result">
        <section><h3>订单 <small>{{result.order_total}} 条</small></h3><button v-for="row in result.orders" :key="row.id" class="search-result" @click="go('/orders',{keyword:'#'+row.id})"><strong>#{{row.id}}</strong><span>{{row.customer_name}} · ¥{{row.total}}</span></button><el-button v-if="result.order_total>5" link type="primary" @click="go('/orders',{keyword:submitted})">查看全部匹配订单</el-button><p v-if="!result.orders.length" class="muted">暂无匹配订单</p></section>
        <section><h3>商品 <small>{{result.product_total}} 个</small></h3><button v-for="row in result.products" :key="row.id" class="search-result" @click="go('/inventory',{keyword:row.sku})"><strong class="mono">{{row.sku}}</strong><span>{{row.name}}</span></button><el-button v-if="result.product_total>5" link type="primary" @click="go('/inventory',{keyword:submitted})">查看全部匹配商品</el-button><p v-if="!result.products.length" class="muted">暂无匹配商品</p></section>
        <section><h3>客户 <small>最多显示 5 项</small></h3><button v-for="row in result.customers" :key="row.id" class="search-result" @click="go('/orders',{customer_id:row.id})"><strong>{{row.name}}</strong><span>查看客户订单 →</span></button><p v-if="!result.customers.length" class="muted">暂无匹配客户</p></section>
      </template><p v-else class="muted">输入关键词后按 Enter 搜索。</p>
    </div>
  </el-dialog>
</template>
<script setup>
import { ref,onMounted,onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
const router=useRouter(),visible=ref(false),keyword=ref(''),submitted=ref(''),result=ref(null),error=ref(''),loading=ref(false),input=ref(null)
let generation=0
function open(){visible.value=true}
async function search(){const id=++generation;result.value=null;error.value='';const term=keyword.value.trim();if(!term){loading.value=false;error.value='请输入搜索关键词';return}loading.value=true;try{const data=await api.get('/search',{params:{keyword:term}});if(id===generation){result.value=data;submitted.value=term}}catch(e){if(id===generation)error.value=e.message}finally{if(id===generation)loading.value=false}}
function go(path,query){visible.value=false;router.push({path,query})}
function shortcut(e){if((e.ctrlKey||e.metaKey)&&!e.altKey&&e.key.toLowerCase()==='k'){e.preventDefault();open()}}
onMounted(()=>window.addEventListener('keydown',shortcut))
onUnmounted(()=>{generation++;window.removeEventListener('keydown',shortcut)})
</script>
