// Run with Playwright available through NODE_PATH; no project dependency changes.
// Uses isolated HTTP fixtures only. Never writes to the business database.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:5178'
const out = process.env.UI_SCREENSHOT_DIR
const warehouses = [{id:1,name:'广州中心仓'},{id:2,name:'佛山周转仓'},{id:3,name:'深圳前置仓'}]
const products = Array.from({length:20},(_,i)=>({id:1000-i,sku:`SKU-${String(1000-i).padStart(5,'0')}`,name:['办公耗材','设备备件','包装材料','智能配件'][i%4]+` ${1000-i}`,price:(80-i*.07).toFixed(2),stocks:warehouses.map(w=>({warehouse_id:w.id,name:w.name,quantity:i===5&&w.id===3?8:i===9&&w.id===2?3:5000}))}))
const orders = Array.from({length:20},(_,i)=>({id:25000-i,customer_name:`模拟企业客户${1000-i}`,warehouse_name:warehouses[i%3].name,operator:'admin',total:(125+i*37.44).toFixed(2),status:i===0||i===5?'pending':i===6?'cancelled':'shipped',created_at:'2026-06-23T14:40:00Z',tracking_no:i===0||i===5||i===6?null:`DEMO-${25000-i}`}))
const lines=[{sku:'SKU-00999',name:'设备备件 0999',quantity:2,unit_price:'79.93'},{sku:'SKU-00480',name:'智能配件 0480',quantity:3,unit_price:'39.98'}]
let browser
const reports=[]
async function setup(role='admin',options={}){
  const context=await browser.newContext({viewport:{width:1920,height:1080},reducedMotion:'reduce'})
  const errors=[], requests=[],state={productMode:'normal',detailMode:'normal',failCreate:false,overviewMode:'normal'}
  await context.addInitScript(({role,options})=>{
    if(role){sessionStorage.setItem('inventory_token','ui-fixture');sessionStorage.setItem('inventory_role',role);sessionStorage.setItem('inventory_user',role)}
    if(options.storageBlocked){Storage.prototype.getItem=new Proxy(Storage.prototype.getItem,{apply(fn,self,args){if(self===localStorage)throw new Error('storage unavailable');return Reflect.apply(fn,self,args)}});Storage.prototype.setItem=new Proxy(Storage.prototype.setItem,{apply(fn,self,args){if(self===localStorage)throw new Error('storage unavailable');return Reflect.apply(fn,self,args)}})}
  },{role,options})
  await context.route('**/api/**',async route=>{
    const req=route.request(), url=new URL(req.url()),p=url.pathname,body=req.postDataJSON()
    requests.push({method:req.method(),path:p,params:Object.fromEntries(url.searchParams),body})
    const ok=data=>route.fulfill({status:200,json:{success:true,data}})
    const fail=message=>route.fulfill({status:503,json:{message,request_id:'ui-test-request'}})
    if(p==='/api/login')return body.password==='bad'?route.fulfill({status:401,json:{message:'用户名或密码错误'}}):ok({token:'ui-fixture',role:'admin',username:'admin'})
    if(p==='/api/overview'){
      if(state.overviewMode==='error')return fail('总览加载失败')
      const days=Number(url.searchParams.get('days')||30)
      if(days===7)await new Promise(r=>setTimeout(r,400))
      return ok({days,order_count:25000,shipped_today:812,available_quantity:15000000,pending_count:128,status_counts:{pending:128,shipped:24512,cancelled:360},trend:Array.from({length:days},(_,i)=>({date:'10-'+String(i+1).padStart(2,'0'),created:i+1,shipped:i})),warehouses:warehouses.map(w=>({...w,order_count:8000})),recent_orders:orders.slice(0,6),generated_at:'2026-10-23T01:00:00Z',timezone:'Asia/Shanghai'})
    }
    if(p==='/api/inventory/summary')return ok({product_count:1000,available_quantity:15000000,low_stock_count:17,warehouse_count:3})
    if(p==='/api/search')return ok({products:[products[0]],orders:[orders[0]],customers:[{id:1,name:'模拟企业客户1000'}],product_total:1,order_total:1})
    if(p==='/api/references')return ok({customers:[{id:1,name:'模拟企业客户1000'}],warehouses})
    if(req.method()==='GET'&&p==='/api/products'){
      if(state.productMode==='error')return fail('数据库不可用')
      if(state.productMode==='empty')return ok({items:[],total:0})
      const keyword=url.searchParams.get('keyword')
      if(keyword==='slow'){await new Promise(r=>setTimeout(r,600));return ok({items:[{...products[0],name:'旧结果'}],total:1})}
      if(keyword==='fast')return ok({items:[{...products[0],name:'新结果'}],total:1})
      return ok({items:products,total:1000})
    }
    if(req.method()==='GET'&&p==='/api/orders')return ok({items:orders.filter(o=>!url.searchParams.get('status')||o.status===url.searchParams.get('status')),total:25000,counts:{all:25000,pending:128,shipped:24512,cancelled:360}})
    if(req.method()==='GET'&&/^\/api\/orders\/\d+$/.test(p)){
      if(state.detailMode==='slow')await new Promise(r=>setTimeout(r,500))
      if(state.detailMode==='error')return fail('明细加载失败')
      return ok(lines)
    }
    if(req.method()==='POST'&&p==='/api/orders'&&state.failCreate)return fail('库存不足，订单未生效')
    if(p.endsWith('/ship')){const order=orders.find(o=>p.includes(`/${o.id}/`));order.status='shipped';order.tracking_no=body.tracking_no}
    if(p.endsWith('/cancel')){const order=orders.find(o=>p.includes(`/${o.id}/`));order.status='cancelled'}
    return ok({id:25001,quantity:5200})
  })
  const page=await context.newPage()
  page.on('pageerror',e=>errors.push(e.message))
  page.on('console',m=>{if((m.type()==='warning'&&/Vue warn/.test(m.text()))||(m.type()==='error'&&!/Failed to load resource/.test(m.text())))errors.push(m.text())})
  return {context,page,requests,state,errors}
}
async function shot(page,name){if(out){await fs.mkdir(out,{recursive:true});await page.screenshot({path:path.join(out,name+'.png'),fullPage:true})}}
async function check(name,fn){await fn();reports.push(name);console.log('PASS',name)}
async function waitLoaded(page){await page.locator('.business-table .el-table__row').first().waitFor()}
async function choose(page,control,text){await control.click();await page.getByRole('option',{name:text,exact:true}).last().click()}
;(async()=>{
  browser=await chromium.launch({channel:process.env.UI_BROWSER_CHANNEL||'msedge',headless:true})
  await check('overview ranges, race protection, error retry, links and account relocation',async()=>{
    const {page,context,requests,state,errors}=await setup()
    await page.goto(base+'/#/overview');await page.locator('.overview-metric strong').filter({hasText:'25,000'}).waitFor()
    assert.equal(await page.locator('.overview-metric').count(),4)
    assert.equal(await page.locator('.topbar .account-role').count(),0)
    assert.equal(await page.locator('.sidebar .account-role').textContent(),'管理员')
    await shot(page,'05-overview')
    await page.getByRole('button',{name:'7 天',exact:true}).click();await page.getByRole('button',{name:'90 天',exact:true}).click()
    await page.waitForTimeout(550);assert.equal(await page.locator('.metric-chart circle').count(),180)
    state.overviewMode='error';await page.getByRole('button',{name:'刷新',exact:true}).click();await page.getByText(/总览加载失败/).waitFor()
    assert.equal(await page.locator('.overview-metric strong').first().textContent(),'—')
    state.overviewMode='normal';await page.getByRole('button',{name:'刷新',exact:true}).click();await page.locator('.metric-chart circle').first().waitFor()
    await page.getByRole('button',{name:'#25000',exact:true}).click();await waitLoaded(page);assert(page.url().includes('keyword=%2325000'))
    await page.getByRole('button',{name:'收起菜单',exact:true}).click();await page.getByRole('button',{name:'账户菜单',exact:true}).click()
    await page.locator('.account-popover').getByText('admin',{exact:true}).waitFor()
    await page.locator('.account-popover').getByRole('button',{name:'退出账号',exact:true}).click();await page.getByRole('heading',{name:'登录',exact:true}).waitFor()
    assert.deepEqual(errors,[]);await context.close()
  })
  await check('search dialog escapes header stacking context on desktop and mobile',async()=>{
    const {page,context,errors}=await setup()
    await page.goto(base+'/#/orders');await waitLoaded(page)
    for(const width of [1920,390]){
      await page.setViewportSize({width,height:850});await page.getByRole('button',{name:'全局搜索',exact:true}).click()
      const dialog=page.getByRole('dialog',{name:'全局搜索',exact:true});await dialog.waitFor()
      assert.equal(await dialog.evaluate(el=>!!el.closest('.topbar')),false)
      const input=page.getByLabel('全局搜索关键词',{exact:true});await input.fill('SKU');await input.press('Enter');await page.locator('.search-result').first().waitFor()
      assert(await input.evaluate(el=>{const r=el.getBoundingClientRect();return r.width>100&&r.top>58&&r.bottom<innerHeight&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===el}))
      await shot(page,'07-search-'+width);await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'})
    }
    await page.getByRole('button',{name:'账户菜单',exact:true}).click();await page.locator('.account-popover').getByText('admin',{exact:true}).waitFor()
    assert.deepEqual(errors,[]);await context.close()
  })
  await check('real summary bindings, status requests and global search navigation',async()=>{
    const {page,context,requests,errors}=await setup()
    await page.goto(base+'/#/inventory');await waitLoaded(page)
    assert.equal(await page.locator('.inventory-summary').count(),3)
    await page.locator('.inventory-summary').filter({hasText:'15,000,000'}).waitFor()
    await page.keyboard.press('Control+k')
    await page.getByLabel('全局搜索关键词',{exact:true}).fill('SKU-01000')
    await page.getByLabel('全局搜索关键词',{exact:true}).press('Enter')
    await page.locator('.search-result').filter({hasText:'SKU-01000'}).click();await waitLoaded(page)
    assert(page.url().includes('keyword=SKU-01000'))
    await page.goto(base+'/#/orders');await waitLoaded(page)
    await page.locator('.status-filters button').filter({hasText:'待发货'}).click()
    await page.waitForTimeout(150)
    assert(requests.some(r=>r.path==='/api/orders'&&r.params.status==='pending'))
    assert.equal(await page.getByRole('link',{name:'数据库实验室',exact:true}).count(),0)
    assert.equal(await page.getByRole('link',{name:'总览',exact:true}).count(),1)
    assert.deepEqual(errors,[]);await context.close()
  })
  await check('login, feedback, expiry, and responsive layout',async()=>{
    const {page,context,requests,errors}=await setup(null)
    await page.goto(base);await page.getByRole('heading',{name:'登录',exact:true}).waitFor()
    assert(!await page.getByText('序仓').count());assert.equal(await page.title(),'企业订单与库存管理')
    await shot(page,'01-login')
    await page.getByLabel('用户名',{exact:true}).fill('admin');await page.getByLabel('密码',{exact:true}).fill('bad')
    await page.getByRole('button',{name:'进入工作台'}).click();await page.getByText('用户名或密码错误').waitFor()
    await page.getByLabel('密码',{exact:true}).fill('fixture-password');await page.getByRole('button',{name:'进入工作台'}).click();await waitLoaded(page)
    assert.deepEqual(requests.filter(r=>r.path==='/api/login').at(-1).body,{username:'admin',password:'fixture-password'})
    await page.evaluate(()=>window.dispatchEvent(new Event('session-expired')));await page.getByText('登录已过期，请重新登录').waitFor()
    await page.setViewportSize({width:390,height:844});assert(!await page.locator('.login-story').isVisible())
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
    await shot(page,'01-login-mobile');assert.deepEqual(errors,[]);await context.close()
  })
  await check('sidebar toggle, Ctrl/Meta+B, focus exclusion, persistence, tooltip and mobile navigation',async()=>{
    const {page,context,errors}=await setup()
    await page.goto(base+'/#/inventory');await waitLoaded(page)
    const toggle=()=>page.getByRole('button',{name:/^(展开|收起)菜单$/})
    assert.equal(await toggle().getAttribute('aria-expanded'),'true')
    await toggle().click();assert.equal(await toggle().getAttribute('aria-expanded'),'false')
    await page.reload();await waitLoaded(page);assert.equal(await toggle().getAttribute('aria-expanded'),'false')
    await page.getByRole('link',{name:'商品与库存',exact:true}).hover();await page.getByRole('tooltip',{name:'商品与库存'}).waitFor()
    await page.getByLabel('搜索商品',{exact:true}).focus();await page.keyboard.press('Control+b');assert.equal(await toggle().getAttribute('aria-expanded'),'false')
    await page.getByRole('heading',{name:'商品与库存',exact:true}).click();await page.keyboard.press('Control+b');assert.equal(await toggle().getAttribute('aria-expanded'),'true')
    await page.keyboard.press('Meta+b');assert.equal(await toggle().getAttribute('aria-expanded'),'false')
    await shot(page,'03-inventory-collapsed')
    await page.getByRole('link',{name:'跳转到业务内容'}).focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content')
    await page.setViewportSize({width:390,height:844});assert(!await toggle().isVisible());assert(await page.locator('.nav-text').first().isVisible())
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await shot(page,'03-inventory-mobile')
    assert.deepEqual(errors,[]);await context.close()
  })
  await check('default collapse without preference and unavailable localStorage',async()=>{
    for(const storageBlocked of [false,true]){
      const {page,context,errors}=await setup('admin',{storageBlocked})
      await page.setViewportSize({width:1000,height:850});await page.goto(base);await waitLoaded(page)
      const toggle=page.getByRole('button',{name:/^(展开|收起)菜单$/})
      assert.equal(await toggle.getAttribute('aria-expanded'),storageBlocked?'true':'false')
      await toggle.click();assert.deepEqual(errors,[]);await context.close()
    }
  })
  await check('inventory admin controls, valid prices, restock and preserved request payloads',async()=>{
    const {page,context,requests,errors}=await setup()
    await page.goto(base+'/#/inventory');await waitLoaded(page)
    assert.equal(await page.locator('.stock-value.low').count(),2)
    await page.getByRole('button',{name:'＋ 新增商品',exact:true}).click()
    const dialog=page.getByRole('dialog'),price=dialog.getByRole('spinbutton',{name:'单价（元）',exact:true})
    for(const amount of ['1.00','12.34','0.01','99999999.99']){await price.fill(amount);assert(await price.evaluate(el=>el.validity.valid))}
    await price.fill('12.34');await dialog.getByLabel('SKU（唯一商品编号）',{exact:true}).fill('TEST-UI');await dialog.getByLabel('商品名称',{exact:true}).fill('测试商品')
    await shot(page,'04-product-dialog');await dialog.getByRole('button',{name:'保存商品',exact:true}).click();await dialog.waitFor({state:'hidden'})
    assert.deepEqual(requests.find(r=>r.method==='POST'&&r.path==='/api/products').body,{id:null,sku:'TEST-UI',name:'测试商品',price:12.34})
    await page.getByRole('button',{name:'编辑',exact:true}).first().click();await page.getByRole('dialog').getByRole('button',{name:'保存商品'}).click()
    assert(requests.some(r=>r.method==='PUT'&&r.path==='/api/products/1000'))
    await page.getByRole('button',{name:'入库',exact:true}).first().click();await page.getByRole('dialog').getByRole('spinbutton').fill('200')
    await shot(page,'04-restock-dialog');await page.getByRole('dialog').getByRole('button',{name:'确认入库'}).click()
    const stock=requests.find(r=>r.path==='/api/stock/restock').body;assert.equal(stock.product_id,1000);assert.equal(stock.warehouse_id,1);assert.equal(stock.quantity,200)
    await page.getByRole('button',{name:'删除',exact:true}).first().click();await page.getByRole('button',{name:'确认删除',exact:true}).click();assert(requests.some(r=>r.method==='DELETE'))
    assert.deepEqual(errors,[]);await context.close()
  })
  await check('inventory race protection, error/empty states, retry and pagination',async()=>{
    const {page,context,requests,state,errors}=await setup()
    await page.goto(base+'/#/inventory');await waitLoaded(page)
    await page.locator('.el-pager li').filter({hasText:/^2$/}).click();await page.waitForTimeout(150)
    assert(requests.some(r=>r.path==='/api/products'&&r.params.page==='2'))
    const search=page.getByLabel('搜索商品',{exact:true})
    await search.fill('slow');await search.press('Enter');await page.waitForTimeout(50);await search.fill('fast');await search.press('Enter')
    await page.getByText('新结果',{exact:true}).waitFor();await page.waitForTimeout(700);assert.equal(await page.getByText('旧结果',{exact:true}).count(),0)
    state.productMode='empty';await page.getByRole('button',{name:'刷新',exact:true}).click();await page.getByText('换个关键词试试').waitFor();await shot(page,'03-inventory-empty')
    state.productMode='error';await page.getByRole('button',{name:'刷新',exact:true}).click();await page.getByText(/数据库不可用/).waitFor();assert(!await page.getByText('暂无匹配商品',{exact:true}).count());await shot(page,'03-inventory-error')
    state.productMode='normal';await search.fill('');await search.press('Enter');await waitLoaded(page);assert.deepEqual(errors,[]);await context.close()
  })
  await check('clerk permissions',async()=>{
    const {page,context,errors}=await setup('clerk');await page.goto(base+'/#/inventory');await waitLoaded(page)
    for(const name of ['＋ 新增商品','编辑','入库','删除'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0)
    await shot(page,'03-inventory-clerk');assert.deepEqual(errors,[]);await context.close()
  })
  await check('order detail loading/error/success and desktop/mobile panel',async()=>{
    const {page,context,state,errors}=await setup();await page.goto(base+'/#/orders');await waitLoaded(page)
    state.detailMode='slow';await page.getByRole('button',{name:'#24999',exact:true}).click();await page.locator('.detail-items .el-loading-mask').waitFor();await page.locator('.detail-table .el-table__row').first().waitFor()
    assert.equal(await page.locator('.selected-order').count(),1)
    await page.evaluate(()=>{window.copiedTracking='';Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.copiedTracking=value}}})})
    await page.getByRole('button',{name:'复制物流单号',exact:true}).click();assert.equal(await page.evaluate(()=>window.copiedTracking),'DEMO-24999')
    await shot(page,'02-orders-detail')
    await page.setViewportSize({width:1100,height:850});assert.equal(await page.locator('.order-detail').evaluate(el=>getComputedStyle(el).position),'fixed')
    await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
    await page.waitForFunction(()=>{const el=document.querySelector('.detail-table');return el.querySelector('.el-table__body').getBoundingClientRect().width<=el.getBoundingClientRect().width+1})
    await shot(page,'02-orders-detail-mobile')
    await page.getByRole('button',{name:'关闭订单详情',exact:true}).click();assert.equal(await page.locator('.order-detail').count(),0)
    state.detailMode='error';await page.getByRole('button',{name:'#24999',exact:true}).click();await page.getByText(/明细加载失败/).waitFor();assert.equal(await page.locator('.detail-table').count(),0)
    assert.deepEqual(errors,[]);await context.close()
  })
  await check('new order form preserves idempotency, failure, quantities, line limit and payload',async()=>{
    const {page,context,requests,state,errors}=await setup();await page.goto(base);await waitLoaded(page)
    await page.getByRole('button',{name:'＋ 新建订单',exact:true}).click();const dialog=page.getByRole('dialog')
    await choose(page,dialog.getByRole('combobox').nth(0),'模拟企业客户1000')
    await choose(page,dialog.getByRole('combobox').nth(2),'SKU-01000 · 办公耗材 1000 · ¥80.00')
    await dialog.getByRole('spinbutton').fill('2');await shot(page,'04-new-order')
    state.failCreate=true;await dialog.getByRole('button',{name:'提交订单'}).click();await dialog.locator('.el-alert').getByText(/库存不足/).waitFor()
    const first=requests.find(r=>r.method==='POST'&&r.path==='/api/orders').body
    assert.match(first.request_key,/^[a-f0-9-]{36}$/);assert.deepEqual(first.items,[{product_id:1000,quantity:2}]);assert.equal(first.customer_id,1);assert.equal(first.warehouse_id,1)
    state.failCreate=false;await dialog.getByRole('button',{name:'提交订单'}).click();await dialog.waitFor({state:'hidden'});assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/api/orders').at(-1).body.request_key,first.request_key)
    await page.getByRole('button',{name:'＋ 新建订单',exact:true}).click()
    assert(await dialog.getByRole('button',{name:'移除',exact:true}).first().isDisabled())
    for(let i=1;i<20;i++)await dialog.getByRole('button',{name:'＋ 添加商品',exact:true}).click()
    assert(await dialog.getByRole('button',{name:'＋ 添加商品',exact:true}).isDisabled());assert.equal(await dialog.locator('.order-line').count(),20)
    await dialog.getByRole('button',{name:'取消',exact:true}).click();assert.deepEqual(errors,[]);await context.close()
  })
  await check('shipment validation and cancel confirmations preserve API behavior',async()=>{
    const {page,context,requests,errors}=await setup();await page.goto(base);await waitLoaded(page)
    await page.getByRole('button',{name:'发货',exact:true}).first().click();const box=page.locator('.shipment-messagebox'),input=box.locator('input')
    await input.fill('x'.repeat(61));await box.getByRole('button',{name:'确认发货'}).click();await box.getByText('请输入 1–60 字符的物流单号').waitFor();assert(!requests.some(r=>r.path.endsWith('/ship')))
    await input.fill('UI-TRACK-001');await shot(page,'04-shipment');await box.getByRole('button',{name:'确认发货'}).click();await box.waitFor({state:'hidden'})
    assert.deepEqual(requests.find(r=>r.path.endsWith('/ship')).body,{tracking_no:'UI-TRACK-001'})
    await page.getByRole('button',{name:'取消',exact:true}).first().click();await shot(page,'04-cancel');await page.getByRole('button',{name:'确认取消',exact:true}).click()
    assert(requests.some(r=>r.path.endsWith('/cancel')));assert.deepEqual(errors,[]);await context.close()
  })
  console.log(JSON.stringify({passed:reports.length,checks:reports},null,2))
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()})
