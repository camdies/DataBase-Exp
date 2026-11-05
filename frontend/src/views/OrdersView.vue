<template>
  <section>
    <div class="page-heading"><div><h1>订单履约</h1><p>管理订单、查看明细并处理发货</p></div><el-button type="primary" @click="openCreate">＋ 新建订单</el-button></div>
    <p v-if="searchKeyword" class="search-context">搜索：{{searchKeyword}} <el-button link type="primary" @click="router.replace({path:'/orders',query:customerFilter?{customer_id:customerFilter}:{}})">清除搜索</el-button></p>
    <div class="orders-layout" :class="{'has-detail':detailDialog}">
      <div class="page-card">
        <div class="table-heading"><h2>{{customerFilter ? '客户订单' : '全部订单'}} <span>{{error ? '—' : total.toLocaleString()}}</span></h2><span class="muted">{{updatedAt ? `更新于 ${updatedAt}` : ''}}</span></div>
        <div class="toolbar orders-toolbar"><div class="status-filters" aria-label="订单状态筛选"><button v-for="option in statusOptions" :key="option.value" type="button" class="filter-pill" :class="{active:statusFilter===option.value}" :aria-pressed="statusFilter===option.value" @click="statusFilter=option.value;page=1;loadData()">{{option.label}} <span>{{loading || error ? '—' : (counts[option.value||'all'] ?? '—')}}</span></button></div><div class="customer-search"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg><el-select v-model="customerFilter" filterable remote clearable :remote-method="searchCustomers" placeholder="按客户姓名搜索" aria-label="按客户筛选" @change="page=1;loadData()"><el-option v-for="c in customers" :key="c.id" :value="c.id" :label="c.name"/></el-select></div><el-button :loading="loading" @click="loadData">刷新</el-button></div>
        <el-alert v-if="lookupError" :title="lookupError" type="error" :closable="false"/>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
        <el-table v-else :data="items" v-loading="loading" empty-text="暂无订单" class="business-table orders-table" height="calc(100dvh - 300px)" :row-class-name="({row})=>detailDialog && selected?.id===row.id?'selected-order':''">
          <el-table-column label="订单" width="100"><template #default="{row}"><el-button class="order-link" link type="primary" @click="detail(row)">#{{row.id}}</el-button></template></el-table-column>
          <el-table-column prop="customer_name" label="客户" min-width="150"/>
          <el-table-column prop="warehouse_name" label="履约仓库" width="125" class-name="secondary-cell"/>
          <el-table-column label="金额（元）" width="110" align="right"><template #default="{row}">{{row.total}}</template></el-table-column>
          <el-table-column label="状态" width="106"><template #default="{row}"><span class="status-pill" :class="row.status">{{labels[row.status]}}</span></template></el-table-column>
          <el-table-column label="下单时间" min-width="162" class-name="secondary-cell"><template #default="{row}">{{new Date(row.created_at).toLocaleString('zh-CN',{hour12:false})}}</template></el-table-column>
          <el-table-column label="操作" width="164"><template #default="{row}"><template v-if="row.status==='pending'"><el-button link type="primary" @click="ship(row)">发货</el-button><el-button link type="danger" @click="cancel(row)">取消</el-button></template><span v-else :class="['muted',{'mono':row.status==='shipped'}]">{{row.status==='shipped'?(row.tracking_no||'—'):'已返还库存'}}</span></template></el-table-column>
        </el-table>
        <el-pagination v-if="!error" v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="loadData"/>
      </div>
      <aside v-if="detailDialog" class="order-detail page-card" aria-labelledby="detail-title" tabindex="-1" @keydown.esc="detailDialog=false">
        <header class="detail-header"><div><h2 id="detail-title">订单 #{{currentOrder?.id}} <span class="status-pill" :class="currentOrder?.status">{{labels[currentOrder?.status]}}</span></h2><p>{{currentOrder?.customer_name}}</p></div><el-button class="detail-close" text aria-label="关闭订单详情" @click="detailDialog=false">×</el-button></header>
        <dl class="detail-meta"><div><dt>履约仓库</dt><dd>{{currentOrder?.warehouse_name}}</dd></div><div><dt>下单时间</dt><dd>{{new Date(currentOrder?.created_at).toLocaleString('zh-CN',{hour12:false})}}</dd></div><div><dt>操作员</dt><dd>{{currentOrder?.operator||'—'}}</dd></div><div><dt>物流单号</dt><dd class="mono">{{currentOrder?.tracking_no||'—'}}</dd></div></dl>
        <div class="detail-items" v-loading="detailLoading">
          <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" show-icon/>
          <template v-else><h3>商品明细 <span class="muted">{{details.length}} 行</span></h3>
            <el-table :data="details" empty-text="暂无商品明细" class="detail-table"><el-table-column label="商品" min-width="100"><template #default="{row}"><strong>{{row.name}}</strong><small class="mono muted">{{row.sku}}</small></template></el-table-column><el-table-column prop="quantity" label="数量" width="48" align="right"/><el-table-column prop="unit_price" label="成交单价" width="70" align="right"/><el-table-column label="小计" width="76" align="right"><template #default="{row}"><strong>{{(row.quantity * Number(row.unit_price)).toFixed(2)}}</strong></template></el-table-column></el-table>
          </template>
        </div>
        <div class="detail-total"><span>订单合计</span><strong>¥{{currentOrder?.total}}</strong></div>
        <div class="order-progress" :class="currentOrder?.status"><span>已下单</span><i aria-hidden="true"></i><strong>{{currentOrder?.status==='cancelled'?'已取消':currentOrder?.status==='shipped'?'已发货':'待发货'}}</strong></div>
        <p class="transaction-note">下单时已在同一事务中扣减{{currentOrder?.warehouse_name}}库存；订单取消后将自动返还。</p>
        <div class="detail-actions"><el-button :disabled="!currentOrder?.tracking_no" @click="copyTracking">复制物流单号</el-button><el-button @click="detailDialog=false">关闭</el-button></div>
      </aside>
    </div>
    <el-dialog v-model="dialog" title="新建订单" width="min(760px, 92vw)" class="order-create-dialog">
      <el-form label-position="top" @submit.prevent="create">
        <div class="form-grid"><el-form-item label="客户"><el-select v-model="form.customer_id" filterable remote :remote-method="searchCustomers" placeholder="输入客户姓名"><el-option v-for="c in customers" :key="c.id" :value="c.id" :label="c.name"/></el-select></el-form-item><el-form-item label="发货仓库"><el-select v-model="form.warehouse_id" aria-label="发货仓库"><el-option v-for="w in warehouses" :key="w.id" :value="w.id" :label="w.name"/></el-select></el-form-item></div>
        <h3 class="form-section-title">商品明细</h3>
        <div v-for="(item,index) in form.items" :key="index" class="order-line"><el-select v-model="item.product_id" filterable remote :remote-method="searchProducts" placeholder="搜索商品名称 / SKU" :aria-label="`第 ${index+1} 行商品`"><el-option v-for="p in products" :key="p.id" :label="`${p.sku} · ${p.name} · ¥${p.price}`" :value="p.id"/></el-select><el-input-number v-model="item.quantity" :min="1" :max="10000" :precision="0" :aria-label="`第 ${index+1} 行数量`"/><el-button text type="danger" :disabled="form.items.length===1" @click="form.items.splice(index,1)">移除</el-button></div>
        <el-button :disabled="form.items.length>=20" @click="form.items.push({product_id:null,quantity:1})">＋ 添加商品</el-button>
        <p class="muted form-note">提交后扣减所选仓库库存；任一商品库存不足，整笔订单不生效。价格以提交时的商品单价为准。</p>
        <el-alert v-if="lookupError" :title="lookupError" type="error" :closable="false"/><el-alert v-if="actionError" :title="actionError" type="error" :closable="false"/>
        <div class="dialog-actions"><el-button @click="dialog=false">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">提交订单</el-button></div>
      </el-form>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed,h,ref,reactive,onMounted,watch } from 'vue'
import { ElMessage,ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useRoute, useRouter } from 'vue-router'
const route=useRoute(), router=useRouter(), statusFilter=ref(''), counts=ref({})
const statusOptions=[{value:'',label:'全部'},{value:'pending',label:'待发货'},{value:'shipped',label:'已发货'},{value:'cancelled',label:'已取消'}]
const searchKeyword=ref(String(route.query.keyword||''))
const items=ref([]),total=ref(0),page=ref(1),customerFilter=ref(route.query.customer_id?Number(route.query.customer_id):null),loading=ref(false),error=ref(''),lookupError=ref(''),actionError=ref(''),saving=ref(false),dialog=ref(false),customers=ref([]),warehouses=ref([]),products=ref([]),details=ref([]),detailDialog=ref(false),detailLoading=ref(false),detailError=ref(''),selected=ref(null),updatedAt=ref('')
const form=reactive({customer_id:null,warehouse_id:1,items:[],request_key:''}),labels={pending:'待发货',shipped:'已发货',cancelled:'已取消'}
let generation=0,customerGeneration=0,productGeneration=0
// UI-only derivation: keep the open panel aligned with refreshed list rows.
const currentOrder=computed(()=>items.value.find(row=>row.id===selected.value?.id)||selected.value)
async function copyTracking(){try{await navigator.clipboard.writeText(currentOrder.value.tracking_no);ElMessage.success('物流单号已复制')}catch{ElMessage.error('无法复制，请手动选择物流单号复制')}}
function uuid(){const b=crypto.getRandomValues(new Uint8Array(16));b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=[...b].map(n=>n.toString(16).padStart(2,'0')).join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`}
async function loadData(){const id=++generation;loading.value=true;error.value='';try{const data=await api.get('/orders',{params:{page:page.value,customer_id:customerFilter.value||undefined,status:statusFilter.value||undefined,keyword:searchKeyword.value||undefined}});if(id===generation){items.value=data.items;total.value=data.total;counts.value=data.counts||{};updatedAt.value=new Date().toLocaleTimeString('zh-CN',{hour12:false})}}catch(e){if(id===generation)error.value=e.message}finally{if(id===generation)loading.value=false}}
async function searchCustomers(keyword=''){const id=++customerGeneration;try{const data=await api.get('/references',{params:{keyword}});if(id===customerGeneration){customers.value=data.customers;warehouses.value=data.warehouses;lookupError.value=''}}catch(e){if(id===customerGeneration)lookupError.value=e.message}}
async function searchProducts(keyword=''){const id=++productGeneration;try{const data=await api.get('/products',{params:{keyword}});if(id===productGeneration){products.value=data.items;lookupError.value=''}}catch(e){if(id===productGeneration)lookupError.value=e.message}}
function openCreate(){Object.assign(form,{customer_id:null,warehouse_id:warehouses.value[0]?.id,items:[{product_id:null,quantity:1}],request_key:uuid()});actionError.value='';dialog.value=true;searchCustomers();searchProducts()}
async function create(){saving.value=true;actionError.value='';try{const result=await api.post('/orders',form);dialog.value=false;page.value=1;customerFilter.value=null;await loadData();window.dispatchEvent(new Event('orders-changed'));ElMessage.success(`订单 #${result.id} 已创建`)}catch(e){actionError.value=e.message}finally{saving.value=false}}
async function detail(row){selected.value=row;details.value=[];detailError.value='';detailDialog.value=true;detailLoading.value=true;try{details.value=await api.get(`/orders/${row.id}`)}catch(e){detailError.value=e.message}finally{detailLoading.value=false}}
async function ship(row){try{const {value}=await ElMessageBox.prompt(h('div',[h('div',{class:'shipment-summary'},[h('strong',`#${row.id}`),h('span',`${row.customer_name} · ${row.warehouse_name}`),h('strong',`¥${row.total}`)]),h('p','请输入唯一物流单号'),h('small',{class:'muted'},'1–60 个字符，需全局唯一。')]),'订单发货',{customClass:'shipment-messagebox',inputPlaceholder:'请输入唯一物流单号',inputValidator:v=>!!v?.trim()&&v.trim().length<=60||'请输入 1–60 字符的物流单号',confirmButtonText:'确认发货',cancelButtonText:'取消'});await api.post(`/orders/${row.id}/ship`,{tracking_no:value});await loadData();window.dispatchEvent(new Event('orders-changed'));ElMessage.success('发货成功')}catch(e){if(e instanceof Error)ElMessage.error(e.message)}}
async function cancel(row){try{await ElMessageBox.confirm(`取消订单 #${row.id} 并返还库存？`,'取消订单',{customClass:'cancel-messagebox',type:'warning',confirmButtonText:'确认取消',cancelButtonText:'返回'});await api.post(`/orders/${row.id}/cancel`);await loadData();window.dispatchEvent(new Event('orders-changed'));ElMessage.success('订单已取消，库存已返还')}catch(e){if(e instanceof Error)ElMessage.error(e.message)}}
watch(()=>[route.query.keyword,route.query.customer_id],()=>{statusFilter.value='';searchKeyword.value=String(route.query.keyword||'');customerFilter.value=route.query.customer_id?Number(route.query.customer_id):null;page.value=1;loadData()})
onMounted(()=>{loadData();searchCustomers()})
</script>

