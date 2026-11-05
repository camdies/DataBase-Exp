<template>
  <section><div class="page-heading"><div><h1>运营总览</h1><p>订单、库存与履约状态一览</p></div><el-button disabled>导出报表</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false"/>
    <el-alert v-else-if="!data" title="页面已准备，等待总览数据接口接入" type="info" :closable="false"/>
    <div v-loading="loading" class="optional-dashboard">
      <div class="summary-grid"><article v-for="m in metrics" :key="m.key" class="inventory-summary page-card"><span class="muted">{{m.title}}</span><div><strong>{{data?.[m.key]?.toLocaleString() ?? '—'}}</strong></div></article></div>
      <div class="optional-grid"><article class="page-card optional-panel"><h2>订单趋势</h2><div class="status-filters"><el-button v-for="days in [7,30,90]" :key="days" :disabled="!data" @click="$emit('range-change',days)">{{days}} 天</el-button></div><MetricChart :rows="data?.trend||[]" :series="[{key:'created',label:'下单量',color:'#2559D6'},{key:'shipped',label:'发货量',color:'#188A5B',dashed:true}]" label="每日下单与发货趋势"/></article><article class="page-card optional-panel"><h2>订单状态分布</h2><div v-for="s in states" :key="s.key" class="optional-row"><span>{{s.label}}</span><strong>{{data?.status_counts?.[s.key]?.toLocaleString() ?? '—'}}</strong></div></article></div>
      <div class="optional-grid"><article class="page-card optional-panel"><h2>分仓履约</h2><div v-for="w in data?.warehouses||[]" :key="w.id" class="optional-row"><span>{{w.name}}</span><strong>{{w.order_count}} 单</strong><div class="metric-track"><i :style="{width: Math.min(100,100*w.order_count/Math.max(1,data.order_count))+'%'}"/></div></div><p v-if="!data?.warehouses?.length" class="table-empty">暂无分仓数据</p></article><article class="page-card optional-panel"><h2>最新订单</h2><el-table :data="data?.recent_orders||[]" empty-text="暂无订单数据"><el-table-column prop="id" label="订单"/><el-table-column prop="customer_name" label="客户"/><el-table-column prop="total" label="金额"/><el-table-column prop="status" label="状态"/></el-table></article></div>
    </div>
  </section>
</template>
<script setup>
import MetricChart from '../components/MetricChart.vue'
const props=defineProps({data:{type:Object,default:null},loading:Boolean,error:{type:String,default:''}})
defineEmits(['range-change'])
const metrics=[{key:'order_count',title:'订单总数'},{key:'shipped_today',title:'今日已发货'},{key:'available_quantity',title:'可用库存'},{key:'pending_count',title:'待处理订单'}]
const states=[{key:'pending',label:'待发货'},{key:'shipped',label:'已发货'},{key:'cancelled',label:'已取消'}]
</script>
