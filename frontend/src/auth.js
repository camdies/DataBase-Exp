import { defineStore } from 'pinia'
import { api } from './api'
export const useAuth=defineStore('auth',{
  state:()=>({token:sessionStorage.getItem('inventory_token')||'', role:sessionStorage.getItem('inventory_role')||'',username:sessionStorage.getItem('inventory_user')||''}),
  actions:{
    async login(form){
      const result=await api.post('/login',form)
      this.token=result.token; this.role=result.role; this.username=result.username
      sessionStorage.setItem('inventory_token',this.token)
      sessionStorage.setItem('inventory_role',this.role)
      sessionStorage.setItem('inventory_user',this.username)
    },
    logout(){this.token='';this.role='';this.username=''; ['inventory_token','inventory_role','inventory_user'].forEach(k=>sessionStorage.removeItem(k))},
  },
})
