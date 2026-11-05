<template>
<section class="model-page">
  <div class="page-heading"><div><h1>模型与代码</h1><p>从关系模型到建表脚本，统一查看与导出 · 版本 {{ model.version || '—' }}</p></div><div class="model-actions"><el-button @click="load" :loading="busy">刷新模型</el-button><el-button @click="validateModel" :loading="validating">校验模型</el-button><el-button v-if="auth.role==='admin'" type="primary" @click="generate" :loading="generating">生成代码</el-button></div></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
  <el-alert v-if="validation" :title="validation.valid?'模型校验通过':'模型校验未通过'" :description="[...validation.checks,...validation.issues,validation.scope].join('；')" :type="validation.valid?'success':'error'" :closable="false" show-icon/>
  <el-tabs v-model="tab" class="model-tabs"><el-tab-pane label="ER 模型" name="model"/><el-tab-pane v-if="auth.role==='admin'" label="代码预览" name="code"/></el-tabs>
  <div v-show="tab==='model'" v-loading="busy" class="model-workspace">
    <aside class="model-objects"><h2>模型对象 <small>{{model.tables.length}}</small></h2><button v-for="t in model.tables" :key="t.name" @click="select(t.name)" :class="{active:selected===t.name}" :aria-pressed="selected===t.name"><span class="table-icon" aria-hidden="true">▦</span><span><strong>{{t.name}}</strong><small>{{t.description}}</small></span></button></aside>
    <div class="model-diagram"><div ref="canvas" class="model-canvas" tabindex="0" aria-label="ER 图画布，可拖动空白平移，也可使用方向键滚动" @pointerdown="panStart" @pointermove="panMove" @pointerup="panEnd" @pointercancel="panEnd" @lostpointercapture="panEnd">
      <svg :width="1120*zoom" :height="800*zoom" viewBox="0 0 1120 800" aria-label="数据库实体关系图">
        <g v-for="e in edges" :key="e.key" class="model-edge"><path :d="e.path"/><rect :x="e.x-6" :y="e.y-16" width="70" height="23" rx="4"/><text :x="e.x" :y="e.y">{{e.label}}</text><title>{{e.title}}</title></g>
        <g v-for="t in model.tables" :key="t.name" class="model-entity" :transform="`translate(${position(t.name).x},${position(t.name).y})`" tabindex="0" role="button" :aria-label="'查看表 '+t.name" :aria-pressed="selected===t.name" @click="select(t.name)" @keydown.enter="select(t.name)" @keydown.space.prevent="select(t.name)">
          <rect width="280" :height="height(t)" rx="10" fill="white" :stroke="selected===t.name?'#2559D6':'#cfd9e8'" stroke-width="2"/>
          <path :d="'M10 0H270Q280 0 280 10V36H0V10Q0 0 10 0'" :fill="selected===t.name?'#2559D6':'#eef3fc'"/>
          <text x="14" y="24" :fill="selected===t.name?'white':'#141d2e'" font-weight="bold">▦ {{t.name}}</text>
          <g v-for="(c,j) in t.columns" :key="c.name"><text x="12" :y="56+j*22" fill="#4a5468">{{c.name}}</text><text x="155" :y="56+j*22" fill="#8590a3" font-size="10">{{c.type}}</text><text x="268" text-anchor="end" :y="56+j*22" fill="#2559D6" font-size="10">{{keys(c).join('/')}}</text></g>
        </g>
      </svg>
    </div><div class="model-controls"><span>拖动空白平移 · 关系按数据库约束推导</span><el-button aria-label="缩小模型" @click="zoom=Math.max(.25,zoom-.1)">−</el-button><b>{{Math.round(zoom*100)}}%</b><el-button aria-label="放大模型" @click="zoom=Math.min(1.8,zoom+.1)">＋</el-button><el-button @click="fit">适应画布</el-button></div></div>
    <aside class="model-properties"><div class="property-heading"><h2>表属性</h2><small>现有模型 · 只读查看</small></div><template v-if="current"><h3><span class="table-icon">▦</span>{{current.name}}<small>{{current.description}}</small></h3>
      <h4>字段定义（{{current.columns.length}}）</h4><div class="property-scroll"><table class="property-table"><thead><tr><th>字段名</th><th>类型</th><th>约束</th><th>说明</th></tr></thead><tbody><tr v-for="c in current.columns" :key="c.name"><td>{{c.name}}</td><td>{{c.type}}</td><td><span class="key-tag" v-for="key in keys(c)" :key="key">{{key}}</span><small>{{c.nullable?'可空':'非空'}}</small></td><td>{{c.description||'—'}}<small v-for="fk in c.references" :key="fk">→ {{fk}}</small></td></tr></tbody></table></div>
      <h4>索引与键约束（{{current.indexes.length}}）</h4><div class="property-scroll"><table class="property-table"><thead><tr><th>索引 / 约束名</th><th>字段</th><th>类型</th></tr></thead><tbody><tr v-for="(i,n) in current.indexes" :key="n"><td>{{i.name}}</td><td>{{i.columns.join(', ')}}</td><td>{{i.kind}}</td></tr></tbody></table></div>
      <h4>检查约束</h4><p v-if="!current.constraints.length" class="muted">无检查约束</p><code class="check-rule" v-for="c in current.constraints" :key="c">{{c}}</code>
      <p class="model-legend">PK 主键 · FK 外键 · UK 单列唯一约束<br>1 : 0..1 表示每条父记录最多有一条子记录；1 : N 表示可有多条（允许零条）。</p>
    </template></aside>
  </div>
  <section v-if="auth.role==='admin'" class="page-card model-code" :class="{'code-expanded':tab==='code'}"><div class="code-toolbar"><el-tabs v-model="file"><el-tab-pane v-for="(label,name) in formats" :key="name" :label="label" :name="name"/></el-tabs><div><el-button @click="copy" :disabled="!files">复制</el-button><el-button @click="download" :disabled="!files">下载当前文件</el-button></div></div><p v-if="!files" class="model-empty">点击“生成代码”后，在这里预览当前真实模型的建表脚本与 ER 图源文件。</p><template v-else><pre tabindex="0" aria-label="生成的代码"><code>{{files[file]}}</code></pre><p class="muted">生成于 {{generatedAt}} · 模型版本 {{version}}</p></template></section>
  <p class="model-note">ⓘ 生成仅导出文件，不执行数据库变更。当前提供只读模型查看，不含模型编辑或生成历史。</p>
</section>
</template>
<script setup>
import {ref,computed,onMounted,onUnmounted,nextTick} from 'vue'
import {ElMessage,ElTabs,ElTabPane} from 'element-plus'
import {api} from '../api'
import {useAuth} from '../auth'
const auth=useAuth(),model=ref({tables:[]}),selected=ref(''),tab=ref('model'),zoom=ref(1),busy=ref(false),generating=ref(false),validating=ref(false),validation=ref(null),error=ref(''),files=ref(null),file=ref('schema_mysql.sql'),version=ref(''),generatedAt=ref(''),canvas=ref(null)
const formats={'schema_mysql.sql':'MySQL','schema_sqlserver.sql':'SQL Server','model.mmd':'Mermaid'}
let generation=0,alive=true,observer,drag=null
const current=computed(()=>model.value.tables.find(t=>t.name===selected.value))
const positions={customer:{x:30,y:30},account:{x:380,y:30},warehouse:{x:730,y:30},sales_order:{x:380,y:260},shipment:{x:730,y:300},product:{x:30,y:520},order_item:{x:380,y:520},stock:{x:730,y:520}}
const position=name=>positions[name]||{x:30,y:30}
const height=t=>48+t.columns.length*22
const keys=c=>[...(c.primary?['PK']:[]),...(c.references.length?['FK']:[]),...(c.unique?['UK']:[])]
const edges=computed(()=>model.value.tables.flatMap(t=>t.columns.flatMap(c=>c.references.map(target=>{
 const parent=model.value.tables.find(p=>p.name===target.split('.')[0]);if(!parent)return null
 const a=position(parent.name),b=position(t.name),h=height(parent);let points
 const pair=parent.name+'>'+t.name
 if(pair==='customer>sales_order')points=[[a.x+140,a.y+h],[a.x+140,220],[b.x+60,220],[b.x+60,b.y]]
 else if(pair==='warehouse>sales_order')points=[[a.x+100,a.y+h],[a.x+100,200],[b.x+230,200],[b.x+230,b.y]]
 else if(pair==='warehouse>stock')points=[[a.x+280,a.y+60],[1080,a.y+60],[1080,b.y+75],[b.x+280,b.y+75]]
 else if(pair==='product>stock')points=[[a.x+140,a.y+h],[a.x+140,760],[b.x+140,760],[b.x+140,b.y+height(t)]]
 else if(pair==='product>order_item'||pair==='sales_order>shipment')points=[[a.x+280,a.y+90],[b.x-25,a.y+90],[b.x-25,b.y+65],[b.x,b.y+65]]
 else points=[[a.x+140,a.y+h],[a.x+140,b.y-45],[b.x+140,b.y-45],[b.x+140,b.y]]
 const one=c.unique||(c.primary&&t.columns.filter(c=>c.primary).length===1),label=one?'1 : 0..1':'1 : N'
 return {key:t.name+c.name+target,path:points.map((p,i)=>(i?'L':'M')+p.join(',')).join(' '),x:pair==='sales_order>shipment'?666:pair==='product>order_item'?315:points[1][0]+8,y:pair==='sales_order>shipment'?292:pair==='product>order_item'?580:points[1][1]-8,label,title:parent.name+' → '+t.name+' '+label}
}))).filter(Boolean))
function select(name){selected.value=name}
async function fit(){await nextTick();if(canvas.value?.clientWidth){zoom.value=Math.max(.25,Math.min(canvas.value.clientWidth/1120,canvas.value.clientHeight/800));canvas.value.scrollTo(0,0)}}
function panStart(e){if(e.button!==0||e.target.closest('.model-entity'))return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:canvas.value.scrollLeft,top:canvas.value.scrollTop};canvas.value.setPointerCapture(e.pointerId)}
function panMove(e){if(!drag)return;canvas.value.scrollLeft=drag.left+drag.x-e.clientX;canvas.value.scrollTop=drag.top+drag.y-e.clientY}
function panEnd(){drag=null}
async function load(){const id=++generation;busy.value=true;error.value='';validation.value=null;files.value=null;try{const value=await api.get('/model');if(alive&&id===generation){model.value=value;selected.value=value.tables.find(t=>t.name===selected.value)?.name||'sales_order';await fit()}}catch(e){if(alive&&id===generation)error.value=e.message}finally{if(alive&&id===generation)busy.value=false}}
async function validateModel(){validating.value=true;error.value='';validation.value=null;try{const result=await api.post('/model/validate');if(alive)validation.value=result}catch(e){if(alive)error.value=e.message}finally{if(alive)validating.value=false}}
async function generate(){generating.value=true;error.value='';files.value=null;try{const result=await api.post('/model/generate');if(alive){files.value=result.files;version.value=result.version;generatedAt.value=new Date().toLocaleString('zh-CN')}}catch(e){if(alive)error.value=e.message}finally{if(alive)generating.value=false}}
async function copy(){try{await navigator.clipboard.writeText(files.value[file.value]);ElMessage.success('代码已复制')}catch{ElMessage.error('浏览器未允许剪贴板访问，请下载文件或选中代码复制')}}
function download(){const url=URL.createObjectURL(new Blob([files.value[file.value]],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=file.value;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
onMounted(()=>{load();observer=new ResizeObserver(()=>{if(!drag)fit()});if(canvas.value)observer.observe(canvas.value)})
onUnmounted(()=>{alive=false;generation++;observer?.disconnect()})
</script>
<style scoped>
.model-actions{display:flex;gap:8px;flex-wrap:wrap}.model-tabs{background:white;padding:0 20px;border-radius:12px;margin:16px 0 12px}.model-tabs :deep(.el-tabs__header){margin:0}.model-workspace{display:grid;grid-template-columns:190px minmax(320px,1fr) 360px;background:white;border:1px solid var(--line);border-radius:14px;overflow:hidden}.model-objects,.model-properties{padding:16px;min-width:0}.model-objects{border-right:1px solid var(--line)}h2{font-size:15px;margin:0 0 16px}h2 small{color:var(--ink-3);font-weight:400;margin-left:6px}.model-objects button{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:1px solid var(--line-2);padding:12px 8px;margin-bottom:8px;background:white;color:var(--ink-2);border-radius:8px;cursor:pointer}.model-objects strong{font-size:12px}.model-objects small{display:block;margin-top:5px;color:var(--ink-3)}.table-icon{font-size:24px;color:var(--primary)}.model-objects button.active{background:var(--primary-soft);border-color:#b8ccfa;color:var(--primary)}.model-diagram{min-width:0;position:relative;background:#f8faff}.model-canvas{height:650px;overflow:auto;background:radial-gradient(#d5deed 1px,transparent 1px);background-size:16px 16px;cursor:grab;touch-action:none}.model-canvas:active{cursor:grabbing}.model-entity{cursor:pointer;font:12px var(--mono)}.model-entity:focus-visible{outline:none}.model-entity:focus-visible>rect{stroke:#e19516;stroke-width:4}.model-edge path{fill:none;stroke:#628ac7;stroke-width:1.7}.model-edge rect{fill:#f8faff}.model-edge text{fill:#2559d6;font-size:10px}.model-controls{display:flex;align-items:center;justify-content:flex-end;gap:6px;padding:10px;border-top:1px solid var(--line)}.model-controls>span{margin-right:auto;font-size:11px;color:var(--ink-3)}.model-controls b{font-size:12px}.model-controls .el-button{margin:0;padding:8px}.model-properties{border-left:1px solid var(--line);max-height:705px;overflow:auto}.property-heading{display:flex;justify-content:space-between;align-items:baseline}.property-heading small{font-size:11px;color:var(--ink-3)}.model-properties h3{font-size:16px;margin:4px 0 22px}.model-properties h3 .table-icon{margin-right:10px}.model-properties h3 small{display:block;font-size:12px;color:var(--ink-3);margin-left:35px;font-weight:400}.model-properties h4{font-size:13px;margin:22px 0 10px}.property-scroll{overflow:auto}.property-table{width:100%;border-collapse:collapse;font-size:11px}.property-table th{background:#f4f6fa;text-align:left;color:var(--ink-2);font-weight:500}.property-table th,.property-table td{border:1px solid var(--line);padding:8px 6px;vertical-align:top;overflow-wrap:anywhere}.property-table small{display:block;font-size:10px;color:var(--ink-3);margin-top:4px}.key-tag{display:inline-block;color:#2559d6;background:#e8effd;padding:1px 3px;border-radius:3px;margin:1px}.check-rule{display:block;background:#f4f6fa;padding:10px;font:11px/1.6 var(--mono);overflow-wrap:anywhere;margin:6px 0}.model-legend,.model-note{font-size:12px;color:var(--ink-3);line-height:1.8}.model-code{margin-top:12px;padding:0 16px 12px}.code-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}.code-toolbar .el-tabs{min-width:220px}.code-toolbar :deep(.el-tabs__header){margin:0}.model-code pre{overflow:auto;max-height:210px;font:12px/1.8 var(--mono);color:#274878;background:#fafcff;padding:12px;tab-size:4}.code-expanded pre{max-height:650px}.model-empty{padding:28px;color:var(--ink-3);font-size:13px}.model-note{padding:8px 12px;background:white;border-radius:8px}@media(min-width:1700px){.model-workspace{grid-template-columns:210px minmax(0,1fr) 420px}}@media(max-width:1250px){.model-workspace{grid-template-columns:170px minmax(0,1fr)}.model-properties{grid-column:1/-1;max-height:none;border-top:1px solid var(--line)}.model-canvas{height:560px}}@media(max-width:720px){.model-workspace{grid-template-columns:1fr}.model-objects{display:flex;flex-wrap:wrap;gap:6px}.model-objects h2{width:100%}.model-objects button{width:auto;margin:0}.model-canvas{height:460px}.model-controls>span{display:none}.code-toolbar{flex-wrap:wrap}.model-properties{padding:12px}}
</style>
