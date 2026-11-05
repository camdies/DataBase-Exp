<template>
  <section>
    <div class="page-heading"><div><h1>商品与库存</h1><p>维护商品档案，查询分仓可用数量</p></div><el-button v-if="auth.role==='admin'" type="primary" @click="edit()">＋ 新增商品</el-button></div>
    <div class="summary-grid" :aria-busy="loading">
      <div v-for="metric in [{key:'product_count',title:'商品档案',unit:'个 SKU',note:'全库商品总数'},{key:'available_quantity',title:'分仓可用总量',unit:'件',note:'全部 '+(summary.warehouse_count ?? '—')+' 个仓库'},{key:'low_stock_count',title:'低库存预警',unit:'个 SKU',note:'各仓合计可用量 < 10'}]" :key="metric.key" class="inventory-summary page-card"><span class="muted">{{metric.title}}</span><div><strong>{{loading || error ? '—' : summary[metric.key]?.toLocaleString() ?? '—'}}</strong><span>{{metric.unit}}</span></div><small class="muted">{{metric.note}}</small></div>
    </div>
    <div class="page-card">
      <div class="table-heading"><h2>商品档案 <span>{{error ? '—' : total.toLocaleString()}}</span></h2><span class="muted">{{updatedAt ? `更新于 ${updatedAt}` : ''}}</span></div>
      <form class="toolbar" @submit.prevent="page=1;loadData()"><el-input v-model="keyword" placeholder="搜索商品名称或 SKU" clearable aria-label="搜索商品" @clear="page=1;loadData()"><template #prefix><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg></template></el-input><el-button native-type="submit" type="primary" plain>查询</el-button><el-button :loading="loading" @click="loadData">刷新</el-button></form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
      <el-table v-else :data="items" v-loading="loading" empty-text="暂无匹配商品" class="business-table inventory-table" height="calc(100dvh - 300px)">
        <template #empty><div class="table-empty"><strong>暂无匹配商品</strong><span>换个关键词试试</span></div></template>
        <el-table-column prop="sku" label="商品编号" width="148" class-name="mono"/>
        <el-table-column prop="name" label="商品名称" min-width="190"/>
        <el-table-column label="单价（元）" width="110" align="right"><template #default="{row}">{{row.price}}</template></el-table-column>
        <el-table-column label="分仓可用库存" min-width="420"><template #default="{row}"><div class="stock-tags"><div v-for="s in row.stocks" :key="s.warehouse_id" class="stock-value" :class="{low:s.quantity<10}"><span class="stock-name">{{s.name}}</span><div class="stock-quantity"><b>{{s.quantity.toLocaleString()}}</b><span v-if="s.quantity<10" class="low-label">低库存</span></div><div class="stock-track" aria-hidden="true"><i :style="{'--stock-fill':Math.max(1.5,Math.min(100,s.quantity/stockScale*100))+'%'}"></i></div></div></div></template></el-table-column>
        <el-table-column v-if="auth.role==='admin'" label="操作" width="180"><template #default="{row}"><el-button link type="primary" @click="edit(row)">编辑</el-button><el-button link type="primary" @click="openStock(row)">入库</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-if="!error" v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="loadData"/>
    </div>
    <el-dialog v-model="dialog" :title="form.id?'编辑商品':'新增商品'" width="min(640px, 92vw)">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="SKU（唯一商品编号）"><el-input v-model="form.sku" class="mono" maxlength="40"/></el-form-item>
        <div class="form-grid product-form-grid"><el-form-item label="商品名称"><el-input v-model="form.name" maxlength="80"/></el-form-item><el-form-item label="单价（元）"><el-input-number v-model="form.price" :min="0.01" :max="99999999.99" :step="0.01" :precision="2"/></el-form-item></div>
        <p class="muted form-note">新增商品的分仓库存均为 0，请通过入库补充数量。</p>
        <el-alert v-if="actionError" :title="actionError" type="error" :closable="false"/>
        <div class="dialog-actions"><el-button @click="dialog=false">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">保存商品</el-button></div>
      </el-form>
    </el-dialog>
    <el-dialog v-model="stockDialog" title="商品入库" width="min(420px, 92vw)">
      <el-form label-position="top" @submit.prevent="restock">
        <p class="stock-product"><strong>{{stockForm.name}}</strong><span class="mono muted">{{items.find(row=>row.id===stockForm.product_id)?.sku}}</span></p>
        <el-form-item label="目标仓库"><el-select v-model="stockForm.warehouse_id"><el-option v-for="w in stockForm.stocks" :key="w.warehouse_id" :label="`${w.name} · 当前 ${w.quantity.toLocaleString()}`" :value="w.warehouse_id"/></el-select></el-form-item>
        <el-form-item label="新增数量"><el-input-number v-model="stockForm.quantity" :min="1" :max="1000000" :precision="0"/></el-form-item>
        <el-alert v-if="actionError" :title="actionError" type="error" :closable="false"/>
        <div class="dialog-actions"><el-button @click="stockDialog=false">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">确认入库</el-button></div>
      </el-form>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { useRoute } from 'vue-router'
const route=useRoute(),summary=ref({})
import { useAuth } from '../auth'
const auth=useAuth(), items=ref([]),total=ref(0),page=ref(1),keyword=ref(String(route.query.keyword||'')),loading=ref(false),error=ref(''),actionError=ref(''),saving=ref(false),dialog=ref(false),stockDialog=ref(false),updatedAt=ref('')
const form=reactive({}),stockForm=reactive({});let generation=0
const stockScale=computed(()=>Math.max(1,...items.value.flatMap(row=>row.stocks.map(stock=>stock.quantity))))
async function loadData(){const id=++generation;loading.value=true;error.value='';try{const [data,stats]=await Promise.all([api.get('/products',{params:{page:page.value,keyword:keyword.value}}),api.get('/inventory/summary')]);if(id===generation){items.value=data.items;total.value=data.total;summary.value=stats;updatedAt.value=new Date().toLocaleTimeString('zh-CN',{hour12:false})}}catch(e){if(id===generation)error.value=e.message}finally{if(id===generation)loading.value=false}}
function edit(row){Object.assign(form,row?{id:row.id,sku:row.sku,name:row.name,price:Number(row.price)}:{id:null,sku:'',name:'',price:1});actionError.value='';dialog.value=true}
function openStock(row){Object.assign(stockForm,{product_id:row.id,name:row.name,stocks:row.stocks,warehouse_id:row.stocks[0]?.warehouse_id,quantity:1});actionError.value='';stockDialog.value=true}
async function save(){saving.value=true;actionError.value='';try{await api[form.id?'put':'post'](form.id?`/products/${form.id}`:'/products',form);dialog.value=false;await loadData();ElMessage.success('商品已保存')}catch(e){actionError.value=e.message}finally{saving.value=false}}
async function restock(){saving.value=true;actionError.value='';try{await api.post('/stock/restock',stockForm);stockDialog.value=false;await loadData();ElMessage.success('入库成功')}catch(e){actionError.value=e.message}finally{saving.value=false}}
async function remove(row){try{await ElMessageBox.confirm(`删除“${row.name}”？仅无库存且无历史订单的商品可删除。`,'删除商品',{type:'warning',confirmButtonText:'确认删除',cancelButtonText:'取消'});await api.delete(`/products/${row.id}`);await loadData();ElMessage.success('商品已删除')}catch(e){if(e instanceof Error)ElMessage.error(e.message)}}
watch(()=>route.query.keyword,()=>{keyword.value=String(route.query.keyword||'');page.value=1;loadData()})
onMounted(loadData)
</script>

