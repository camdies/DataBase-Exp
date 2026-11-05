<template>
  <section><div class="page-heading"><div><h1>数据库实验室</h1><p>事务、索引与并发访问的可复现实验</p></div><div><el-button disabled>导出测试报告</el-button><el-button type="primary" disabled>运行全部测试</el-button></div></div>
    <el-alert v-if="error||!data" :title="error||'页面已准备，实验执行接口尚未接入'" :type="error?'error':'info'" :closable="false"/>
    <div v-loading="loading" class="optional-dashboard"><div class="summary-grid"><article v-for="metric in metrics" :key="metric.key" class="inventory-summary page-card"><span class="muted">{{metric.label}}</span><div><strong>{{data?.[metric.key] ?? '—'}}</strong></div></article></div>
    <div class="optional-grid"><article class="page-card optional-panel"><h2>事务演示</h2><section v-for="run in data?.transactions||[]" :key="run.id"><h3>{{run.outcome}}</h3><ol><li v-for="step in run.steps" :key="step.name">{{step.name}} · {{step.result}}</li></ol></section><p v-if="!data?.transactions?.length" class="table-empty">暂无已执行的事务实验</p></article><article class="page-card optional-panel"><h2>索引对比</h2><el-table :data="data?.index_comparisons||[]" empty-text="暂无真实测量结果"><el-table-column prop="query_name" label="查询"/><el-table-column prop="without_index_ms" label="无索引 ms"/><el-table-column prop="with_index_ms" label="有索引 ms"/></el-table></article></div>
    <div class="optional-grid"><article class="page-card optional-panel"><h2>并发访问性能</h2><MetricChart :rows="data?.concurrency||[]" :series="[{key:'qps',label:'QPS',color:'#2559D6'}]" x-key="clients" label="并发客户端数量与吞吐量"/><el-table :data="data?.concurrency||[]" empty-text="暂无压测记录"><el-table-column prop="clients" label="客户端数"/><el-table-column prop="qps" label="QPS"/><el-table-column prop="p95_ms" label="p95 ms"/><el-table-column prop="error_rate" label="错误率"/></el-table></article><article class="page-card optional-panel"><h2>数据模型</h2><div v-for="entity in data?.entities||[]" :key="entity.name" class="optional-row"><strong>{{entity.name}}</strong><span>{{entity.row_count}} 行</span></div><p v-if="!data?.entities?.length" class="table-empty">等待模型元数据与关系图</p></article></div></div>
  </section>
</template>
<script setup>
import MetricChart from '../components/MetricChart.vue'
defineProps({data:{type:Object,default:null},loading:Boolean,error:{type:String,default:''}})
const metrics=[{key:'row_count',label:'数据规模'},{key:'transaction_passed',label:'事务一致性'},{key:'retry_count',label:'死锁 / 重试次数'},{key:'peak_qps',label:'峰值吞吐'}]
</script>
