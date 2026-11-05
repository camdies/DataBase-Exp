"""真实 MySQL 集成测试。仅允许独立的 *_test 数据库；缺配置直接报错。"""
import os
import secrets
import unittest
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import create_engine, insert, select, update, func, text
from sqlalchemy.exc import OperationalError, IntegrityError, TimeoutError as PoolTimeout
from backend.app import create_app
from backend.models import metadata, account, customer, product, warehouse, stock, sales_order, order_item, shipment
from backend.security import hash_password
from backend.controllers import InventoryController
from backend.validation import Problem
from tools.manage import ddl_demo, create_user
from tools.access_report import report


class MySQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ['TEST_DATABASE_URL'], isolation_level='READ COMMITTED', pool_size=12)
        if cls.engine.dialect.name != 'mysql' or not cls.engine.url.database.endswith('_test'):
            raise RuntimeError('测试只允许 MySQL 且数据库名必须以 _test 结尾')
        cls.password = secrets.token_urlsafe(18)
        cls.hashed = hash_password(cls.password)
        cls.secret = secrets.token_urlsafe(40)
        cls.logs = tempfile.TemporaryDirectory()
        cls.app = create_app(cls.engine, cls.secret, cls.logs.name)
        cls.controller = InventoryController(cls.engine)
        cls.admin = {'id':1,'role':'admin'}
        cls.clerk = {'id':2,'role':'clerk'}

    def setUp(self):
        metadata.drop_all(self.engine)
        metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(insert(account),[{'id':i,'username':role,'password_hash':self.hashed,'role':role} for i,role in [(1,'admin'),(2,'clerk')]])
            c.execute(insert(customer),{'id':1,'name':'测试客户','phone':'TEST','address':'测试地址'})
            c.execute(insert(warehouse),{'id':1,'name':'测试仓'})
            c.execute(insert(product),[{'id':i,'sku':f'TEST-{i}','name':f'商品{i}','price':10} for i in [1,2]])
            c.execute(insert(stock),[{'warehouse_id':1,'product_id':i,'quantity':5} for i in [1,2]])
        self.client = self.app.test_client()

    @classmethod
    def tearDownClass(cls):
        metadata.drop_all(cls.engine)
        cls.engine.dispose()
        cls.app.extensions['access_log_handler'].close()
        cls.logs.cleanup()

    def payload(self, quantity=1, items=None):
        return {'customer_id':1,'warehouse_id':1,'request_key':str(uuid4()),'items':items or [{'product_id':1,'quantity':quantity}]}

    def headers(self, username='admin'):
        response=self.client.post('/api/login',json={'username':username,'password':self.password})
        self.assertEqual(response.status_code,200)
        return {'Authorization':'Bearer '+response.json['data']['token']}

    def balance(self,pid=1):
        with self.engine.connect() as c:
            return c.scalar(select(stock.c.quantity).where(stock.c.product_id==pid))

    def test_create_cancel_is_atomic_and_cannot_cancel_twice(self):
        oid=self.controller.create_order(self.clerk,self.payload(3))['id']
        self.assertEqual(self.balance(),2)
        self.controller.transition(self.clerk,oid,'cancel',{})
        self.assertEqual(self.balance(),5)
        with self.assertRaises(Problem): self.controller.transition(self.clerk,oid,'cancel',{})
        self.assertEqual(self.balance(),5)

    def test_second_item_shortage_rolls_back_first_item_and_order(self):
        with self.assertRaises(Problem):
            self.controller.create_order(self.clerk,self.payload(items=[{'product_id':1,'quantity':2},{'product_id':2,'quantity':6}]))
        self.assertEqual(self.balance(),5)
        with self.engine.connect() as c:
            self.assertEqual(c.scalar(select(func.count()).select_from(sales_order)),0)
            self.assertEqual(c.scalar(select(func.count()).select_from(order_item)),0)

    def test_duplicate_request_does_not_deduct_again(self):
        payload=self.payload(2);h=self.headers()
        self.assertEqual(self.client.post('/api/orders',json=payload,headers=h).status_code,201)
        self.assertEqual(self.client.post('/api/orders',json=payload,headers=h).status_code,409)
        self.assertEqual(self.balance(),3)

    def test_two_clients_race_for_last_stock(self):
        with self.engine.begin() as c: c.execute(update(stock).values(quantity=1))
        barrier=Barrier(2)
        def run(actor):
            barrier.wait()
            try:
                self.controller.create_order(actor,self.payload());return 'ok'
            except Problem as e: return e.code
        with ThreadPoolExecutor(max_workers=2) as p: results=list(p.map(run,[self.admin,self.clerk]))
        self.assertCountEqual(results,['ok','INSUFFICIENT_STOCK'])
        self.assertEqual(self.balance(),0)

    def test_two_clients_cancel_once(self):
        oid=self.controller.create_order(self.clerk,self.payload(2))['id'];barrier=Barrier(2)
        def run(_):
            barrier.wait()
            try: self.controller.transition(self.clerk,oid,'cancel',{});return 'ok'
            except Problem as e: return e.code
        with ThreadPoolExecutor(max_workers=2) as p: result=list(p.map(run,range(2)))
        self.assertCountEqual(result,['ok','INVALID_STATE']);self.assertEqual(self.balance(),5)

    def test_shipment_one_to_one_and_history_price(self):
        oid=self.controller.create_order(self.clerk,self.payload(2))['id']
        self.controller.save_product(self.admin,{'sku':'TEST-1','name':'已更名','price':'22.00'},1)
        self.assertEqual(str(self.controller.detail(self.admin,oid)[0]['unit_price']),'10.00')
        self.controller.transition(self.clerk,oid,'ship',{'tracking_no':'SHIP-1'})
        with self.assertRaises(Problem): self.controller.transition(self.clerk,oid,'ship',{'tracking_no':'SHIP-2'})
        with self.engine.connect() as c: self.assertEqual(c.scalar(select(func.count()).select_from(shipment)),1)
        rows=self.controller.orders(self.admin)['items'];self.assertEqual(str(rows[0]['total']),'20.00')
        self.assertEqual(rows[0]['customer_name'],'测试客户')

    def test_product_crud_delete_guards_and_restock(self):
        pid=self.controller.save_product(self.admin,{'sku':'NEW','name':'新商品','price':1})['id']
        self.controller.delete_product(self.admin,pid)
        with self.assertRaises(Problem): self.controller.delete_product(self.admin,1)
        self.controller.restock(self.admin,{'product_id':1,'warehouse_id':1,'quantity':2})
        self.assertEqual(self.balance(),7)

    def test_invalid_input_and_injection_are_data(self):
        h=self.headers()
        for value in [0,-1,1.5,True,None,'abc']:
            p=self.payload();p['items'][0]['quantity']=value
            self.assertEqual(self.client.post('/api/orders',headers=h,json=p).status_code,422)
        for price in ['NaN','Infinity','1.001','-2',None]:
            self.assertEqual(self.client.post('/api/products',headers=h,json={'sku':'X','name':'X','price':price}).status_code,422)
        self.assertEqual(self.client.get('/api/products',headers=h,query_string={'keyword':"' OR 1=1 --"}).json['data']['total'],0)
        self.assertEqual(self.client.post('/api/orders',headers=h,json=[]).status_code,422)

    def test_missing_resources_and_duplicate_items(self):
        h=self.headers()
        p=self.payload();p['customer_id']=999
        self.assertEqual(self.client.post('/api/orders',headers=h,json=p).status_code,404)
        p=self.payload(items=[{'product_id':1,'quantity':1}]*2)
        self.assertEqual(self.client.post('/api/orders',headers=h,json=p).status_code,422)
        self.assertEqual(self.client.get('/api/orders/999',headers=h).status_code,404)

    def test_fail_closed_db_outage_and_weak_secret(self):
        with self.assertRaises(RuntimeError): create_app(self.engine,'weak')
        h=self.headers()
        with patch.object(self.engine,'connect',side_effect=OperationalError('test',{},Exception('offline'))):
            r=self.client.get('/api/products',headers=h)
            self.assertEqual(r.status_code,503);self.assertFalse(r.json['success'])

    def test_access_policy_closure_and_direct_controller_denial(self):
        manifest={'model_validate':('POST','/api/model/validate'),'model_metadata':('GET','/api/model'),'model_generate':('POST','/api/model/generate'),'references':('GET','/api/references'), 'products':('GET','/api/products'),
            'create_product':('POST','/api/products'),'edit_product':('PUT','/api/products/1'),
            'delete_product':('DELETE','/api/products/1'),'restock':('POST','/api/stock/restock'),
            'overview':('GET','/api/overview'),'search':('GET','/api/search?keyword=TEST'),
            'inventory_summary':('GET','/api/inventory/summary'),
            'orders':('GET','/api/orders'),'create_order':('POST','/api/orders'),
            'detail':('GET','/api/orders/1'),'ship':('POST','/api/orders/1/ship'),'cancel':('POST','/api/orders/1/cancel')}
        endpoints={r.endpoint.removeprefix('api.') for r in self.app.url_map.iter_rules() if r.endpoint.startswith('api.') and r.endpoint!='api.login'}
        self.assertEqual(endpoints,set(manifest))
        h=self.headers('clerk')
        for name,(method,path) in manifest.items():
            self.assertEqual(self.client.open(path,method=method,json={}).status_code,401,name)
            if name in ['create_product','edit_product','delete_product','restock','model_generate']:
                self.assertEqual(self.client.open(path,method=method,json={},headers=h).status_code,403,name)
        with self.assertRaises(Problem): self.controller.save_product(self.clerk,{'sku':'x','name':'x','price':2})

    def test_ddl_lifecycle_and_preserve_business_tables(self):
        self.assertTrue(ddl_demo(self.engine)['drop'])
        self.assertEqual(self.controller.products(self.admin)['total'],2)

    def records(self):
        return [json.loads(line) for path in Path(self.logs.name).glob('*.jsonl') for line in path.read_text(encoding='utf-8').splitlines()]

    def test_persistent_access_logs_account_client_sql_and_error(self):
        h = self.headers('clerk')
        h.update({'X-Client-ID':'client-001', 'X-Benchmark-ID':'regression', 'User-Agent':'Mozilla/5.0 (Windows NT 10.0)', 'X-Forwarded-For':'spoofed'})
        good = self.client.get('/api/products?keyword=private-search-value', headers=h)
        denied = self.client.post('/api/products', json={'password':'private-body'}, headers=h)
        by_id = {r['request_id']:r for r in self.records()}
        row = by_id[good.headers['X-Request-ID']]
        self.assertEqual(row['username'], 'clerk'); self.assertEqual(row['client_id'], 'client-001')
        self.assertEqual(row['client_os'], 'Windows'); self.assertEqual(row['remote_ip'], '127.0.0.1')
        self.assertGreaterEqual(row['sql_count'], 2); self.assertGreater(row['sql_ms'], 0)
        self.assertIn('sql;dur=', good.headers['Server-Timing'])
        self.assertEqual(by_id[denied.headers['X-Request-ID']]['status'],403)
        content = json.dumps(list(by_id.values()))
        for secret in [self.password, h['Authorization'][7:], 'private-body', 'private-search-value']:
            self.assertNotIn(secret,content)
        summary = report(self.logs.name, 'regression')
        self.assertEqual(summary['overall']['requests'],2)
        self.assertEqual(summary['overall']['errors'],1)

    def test_database_failure_and_unmatched_path_are_logged(self):
        h = self.headers()
        with patch.object(self.engine,'connect',side_effect=OperationalError('secret-sql',{},Exception('offline'))):
            result=self.client.get('/api/products',headers=h)
        missing=self.client.get('/api/does-not-exist/private-value')
        records={r['request_id']:r for r in self.records()}
        self.assertEqual(records[result.headers['X-Request-ID']]['status'],503)
        self.assertEqual(records[missing.headers['X-Request-ID']]['route'],'<unmatched>')

    def test_new_independent_account_and_password_whitespace(self):
        password='  '+self.password+'  '
        user=create_user(self.engine,'warehouse-clerk',password)
        response=self.client.post('/api/login',json={'username':user['username'],'password':password})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['data']['role'],'clerk')
        self.assertEqual(self.client.post('/api/login',json={'username':user['username'],'password':password.strip()}).status_code,401)
        with self.assertRaises(IntegrityError): create_user(self.engine,'warehouse-clerk',password)
        with self.assertRaises(ValueError): create_user(self.engine,'other',password,'root')

    def test_log_failure_does_not_misrepresent_committed_write(self):
        h=self.headers()
        with patch.object(self.app.extensions['access_log'],'info',side_effect=OSError('disk full')):
            response=self.client.post('/api/orders',headers=h,json=self.payload())
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.headers['X-Access-Log-Status'],'failed')
        self.assertEqual(self.balance(),4)

    def test_pool_exhaustion_is_service_unavailable(self):
        h=self.headers()
        with patch.object(self.engine,'connect',side_effect=PoolTimeout('exhausted')):
            response=self.client.get('/api/products',headers=h)
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json['code'],'DATABASE_BUSY')


if __name__ == '__main__': unittest.main()
