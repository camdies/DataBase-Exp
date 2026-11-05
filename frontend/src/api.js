import axios from 'axios'
export const api = axios.create({baseURL:'/api',timeout:15000})
// getRandomValues 在局域网 HTTP 下也可用；不依赖仅安全上下文支持的 randomUUID。
let clientId=sessionStorage.getItem('inventory_client')
if(!clientId){
  clientId=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('')
  sessionStorage.setItem('inventory_client',clientId)
}
api.interceptors.request.use(config=>{
  config.headers['X-Client-ID']=clientId
  const token=sessionStorage.getItem('inventory_token')
  if(token) config.headers.Authorization=`Bearer ${token}`
  return config
})
api.interceptors.response.use(response=>response.data.data,error=>{
  const body=error.response?.data
  const message=body?.message || '网络连接失败，请检查服务器后重试'
  const e=new Error(message+(body?.request_id ? `（请求 ${body.request_id}）` : ''))
  e.status=error.response?.status
  if(e.status===401 && error.config?.url!='/login') window.dispatchEvent(new Event('session-expired'))
  return Promise.reject(e)
})
