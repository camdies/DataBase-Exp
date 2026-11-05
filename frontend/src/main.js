import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElInputNumber,
  ElOption, ElPagination, ElSelect, ElTable, ElTableColumn, ElTag, ElLoading } from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/coursework.css'
import App from './App.vue'
const router = createRouter({history:createWebHashHistory(),routes:[
  {path:'/',redirect:'/orders'},
  {path:'/model',component:()=>import('./views/ModelView.vue')},
  {path:'/overview',component:()=>import('./views/OverviewView.vue')},
  {path:'/orders',component:()=>import('./views/OrdersView.vue')},
  {path:'/inventory',component:()=>import('./views/InventoryView.vue')},
  {path:'/:pathMatch(.*)*',redirect:'/orders'},
]})
const app=createApp(App).use(createPinia()).use(router)
for(const component of [ElAlert,ElButton,ElDialog,ElForm,ElFormItem,ElInput,ElInputNumber,ElOption,ElPagination,ElSelect,ElTable,ElTableColumn,ElTag]) app.component(component.name,component)
app.use(ElLoading).mount('#app')
