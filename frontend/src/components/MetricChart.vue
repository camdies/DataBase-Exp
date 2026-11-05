<template>
  <div class="metric-chart">
    <div class="chart-legend"><span v-for="line in series" :key="line.key"><i :style="{background:line.color}"/>{{line.label}}</span></div>
    <svg v-if="rows.length" viewBox="0 0 640 240" role="img" :aria-label="label">
      <g v-for="tick in [0,1,2,3,4]" :key="tick"><line x1="48" x2="620" :y1="200-tick*44" :y2="200-tick*44" stroke="var(--line)" stroke-dasharray="3 4"/><text x="40" :y="204-tick*44" text-anchor="end">{{Math.round(max*tick/4).toLocaleString()}}</text></g>
      <g v-for="line in series" :key="line.key"><polyline :points="points(line.key)" fill="none" :stroke="line.color" stroke-width="2.5" :stroke-dasharray="line.dashed?'5 4':undefined"/><circle v-for="(row,i) in rows" :key="i" :cx="x(i)" :cy="y(row[line.key])" r="3" fill="white" :stroke="line.color"><title>{{row[xKey]}} · {{line.label}}：{{row[line.key]}}</title></circle></g>
      <text v-for="i in labels" :key="i" :x="x(i)" y="228" text-anchor="middle">{{rows[i][xKey]}}</text>
    </svg><p v-else class="table-empty">暂无测量数据</p>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props=defineProps({rows:{type:Array,default:()=>[]},series:{type:Array,required:true},xKey:{type:String,default:'date'},label:{type:String,required:true}})
const max=computed(()=>Math.max(1,...props.rows.flatMap(row=>props.series.map(line=>Number(row[line.key])||0))))
const labels=computed(()=>[...new Set([0,Math.floor((props.rows.length-1)/2),props.rows.length-1])].filter(i=>i>=0))
const x=i=>48+i*572/Math.max(1,props.rows.length-1)
const y=value=>200-(Number(value)||0)*176/max.value
const points=key=>props.rows.map((row,i)=>`${x(i)},${y(row[key])}`).join(' ')
</script>
