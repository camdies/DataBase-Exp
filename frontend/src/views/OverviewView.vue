<template>
  <section>
    <div class="page-heading"><div><h1>运营总览</h1><p>订单、库存与履约状态一览<span v-if="data"> · 更新于 {{formatTime(data.generated_at)}}</span></p></div><div class="overview-actions"><el-button :loading="loading" @click="load">刷新</el-button><el-button type="primary" @click="router.push('/orders')">查看订单 →</el-button></div></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
    <div v-loading="loading" class="overview-dashboard" :aria-busy="loading">
      <div class="overview-metrics"><article v-for="metric in metrics" :key="metric.key" class="page-card overview-metric"><span class="metric-label"><i :style="{'--metric-color':metric.color}"/>{{metric.label}}</span><div><strong>{{!error && data ? data[metric.key].toLocaleString() : '—'}}</strong><span>{{metric.unit}}</span></div><p>{{metric.note}}</p></article></div>
      <div class="overview-top-grid">
        <article class="page-card overview-panel"><div class="overview-panel-heading"><h2>订单趋势 <small>近 {{days}} 天 · 上海时区</small></h2><div class="range-controls" aria-label="趋势时间范围"><button v-for="d in [7,30,90]" :key="d" :aria-pressed="days===d" :class="{active:days===d}" @click="days=d;load()">{{d}} 天</button></div></div>
          <MetricChart :rows="safeData?.trend||[]" :series="series" label="每日下单量与发货量趋势"/>
          <p v-if="safeData && !hasEvents" class="muted overview-trend-note">当前时间范围内暂无下单或发货记录。</p>
          <details v-if="safeData" class="trend-data"><summary>查看每日数据</summary><div><table><caption>近 {{days}} 天的真实下单与发货数量</caption><thead><tr><th>日期</th><th>下单量</th><th>发货量</th></tr></thead><tbody><tr v-for="row in safeData.trend" :key="row.date"><td>{{row.date}}</td><td>{{row.created}}</td><td>{{row.shipped}}</td></tr></tbody></table></div></details>
        </article>
        <article class="page-card overview-panel"><div class="overview-panel-heading"><h2>订单状态分布</h2><span class="muted">全部历史订单</span></div><div class="status-stack" aria-hidden="true"><i v-for="s in states" :key="s.key" :class="s.key" :style="{width:percent(safeData?.status_counts[s.key])+'%'}"/></div><div v-for="s in states" :key="s.key" class="distribution-row"><span><i :class="s.key"/>{{s.label}}</span><strong>{{safeData ? safeData.status_counts[s.key].toLocaleString() : '—'}}</strong><span class="muted">{{safeData ? percent(safeData.status_counts[s.key]).toFixed(1)+'%' : '—'}}</span></div><p v-if="safeData?.order_count===0" class="muted">暂无订单，创建订单后会显示状态占比。</p></article>
      </div>
      <div class="overview-bottom-grid">
        <article class="page-card overview-panel"><div class="overview-panel-heading"><h2>分仓履约</h2><span class="muted">全部订单占比</span></div><div v-for="(w,index) in safeData?.warehouses||[]" :key="w.id" class="warehouse-distribution"><div><strong>{{w.name}}</strong><span>{{w.order_count.toLocaleString()}} 单 · {{percent(w.order_count).toFixed(1)}}%</span></div><div class="metric-track"><i :style="{width:percent(w.order_count)+'%',background:warehouseColors[index%warehouseColors.length]}"/></div></div><p v-if="!safeData?.warehouses?.length" class="table-empty">暂无分仓数据</p></article>
        <article class="page-card overview-recent"><div class="overview-panel-heading"><h2>最新订单</h2><el-button link type="primary" @click="router.push('/orders')">查看全部 →</el-button></div><el-table :data="safeData?.recent_orders||[]" empty-text="暂无订单数据"><el-table-column label="订单" width="90"><template #default="{row}"><el-button link type="primary" class="order-link" @click="router.push({path:'/orders',query:{keyword:'#'+row.id}})">#{{row.id}}</el-button></template></el-table-column><el-table-column prop="customer_name" label="客户" min-width="155"/><el-table-column prop="warehouse_name" label="履约仓库" min-width="115"/><el-table-column label="金额（元）" align="right" width="110"><template #default="{row}">{{row.total}}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{row}"><span class="status-pill" :class="row.status">{{statusLabels[row.status]}}</span></template></el-table-column><el-table-column label="下单时间" width="130"><template #default="{row}"><span class="secondary-cell">{{formatTime(row.created_at)}}</span></template></el-table-column></el-table></article>
      </div>
    </div>
  </section>
</template>
<script setup>
import { computed,ref,onMounted,onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import MetricChart from '../components/MetricChart.vue'
const router=useRouter(),days=ref(30),data=ref(null),loading=ref(false),error=ref('')
const safeData=computed(()=>error.value?null:data.value)
let generation=0
async function load(){const id=++generation;loading.value=true;error.value='';data.value=null;try{const result=await api.get('/overview',{params:{days:days.value}});if(id===generation)data.value=result}catch(e){if(id===generation)error.value=e.message}finally{if(id===generation)loading.value=false}}
const metrics=[{key:'order_count',label:'订单总数',unit:'单',note:'全部历史订单，含已取消',color:'#2559D6'},{key:'shipped_today',label:'今日已发货',unit:'单',note:'按上海时区当日发货时间统计',color:'#188A5B'},{key:'available_quantity',label:'可用库存',unit:'件',note:'全部仓库当前可用量合计',color:'#6C52BE'},{key:'pending_count',label:'待处理订单',unit:'单',note:'当前待发货订单',color:'#B8730A'}]
const states=[{key:'shipped',label:'已发货'},{key:'pending',label:'待发货'},{key:'cancelled',label:'已取消'}],statusLabels={pending:'待发货',shipped:'已发货',cancelled:'已取消'}
const series=[{key:'created',label:'下单量',color:'#2559D6'},{key:'shipped',label:'发货量',color:'#188A5B',dashed:true}],warehouseColors=['#2559D6','#6C52BE','#188A5B']
const percent=count=>100*(count||0)/Math.max(1,safeData.value?.order_count||0)
const hasEvents=computed(()=>safeData.value?.trend.some(row=>row.created||row.shipped))
const formatTime=value=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
onMounted(load)
onUnmounted(()=>{generation++})
</script>
