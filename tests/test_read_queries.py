"""Read-only endpoint regression tests with isolated SQLite fixtures, not MySQL lock tests."""
import secrets
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from sqlalchemy import create_engine, insert, update, delete
from backend.app import create_app
from backend.models import metadata, account, customer, warehouse, product, stock, sales_order, order_item, shipment
from backend.security import issue_token


class ReadQueryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        metadata.create_all(self.engine)
        self.logs = tempfile.TemporaryDirectory()
        self.app = create_app(self.engine, secrets.token_urlsafe(48), self.logs.name)
        self.client = self.app.test_client()
        with self.engine.begin() as c:
            c.execute(insert(account), [{'id': i, 'username': role, 'role': role, 'password_hash': 'unused'} for i, role in [(1, 'admin'), (2, 'clerk')]])
            c.execute(insert(customer), [{'id': i, 'name': name, 'phone': '', 'address': ''} for i, name in [(1, '甲客户'), (2, '乙客户')]])
            c.execute(insert(warehouse), [{'id': i, 'name': str(i)} for i in range(1, 4)])
            c.execute(insert(product), [{'id': i, 'sku': f'SKU-{i}', 'name': '物品', 'price': 2} for i in range(1, 25)])
            # Product 1 totals 10 (not low despite a zero warehouse); 2 totals 9; 3 totals 0.
            c.execute(insert(stock), [{'warehouse_id': w, 'product_id': p, 'quantity': ([0, 5, 5] if p == 1 else [3, 3, 3] if p == 2 else [0, 0, 0] if p == 3 else [10, 10, 10])[w-1]} for p in range(1, 25) for w in range(1, 4)])
            c.execute(insert(sales_order), [{'id': i, 'request_key': str(i), 'customer_id': 1 if i < 3 else 2, 'warehouse_id': 1, 'created_by': 1, 'status': status, 'created_at': datetime(2026, 1, 1)} for i, status in [(1, 'pending'), (2, 'shipped'), (3, 'cancelled')]])
            c.execute(insert(order_item), [{'order_id': i, 'product_id': p, 'quantity': 1, 'unit_price': 2} for i, p in [(1, 1), (1, 2), (2, 1), (3, 3)]])
        with self.app.app_context():
            self.headers = {'Authorization': 'Bearer ' + issue_token({'id': 2})}

    def tearDown(self):
        self.app.extensions["access_log_handler"].close()
        self.engine.dispose()
        self.logs.cleanup()

    def get(self, path):
        response = self.client.get('/api' + path, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['data']

    def test_summary_is_global_and_low_stock_uses_combined_warehouses(self):
        self.assertEqual(self.get('/inventory/summary'), {'product_count': 24, 'available_quantity': 649, 'low_stock_count': 2, 'warehouse_count': 3})
        self.assertEqual(len(self.get('/products')['items']), 20)

    def test_status_counts_keep_customer_scope_but_ignore_active_status(self):
        data = self.get('/orders?customer_id=1&status=pending')
        self.assertEqual(data['counts'], {'all': 2, 'pending': 1, 'shipped': 1, 'cancelled': 0})
        self.assertEqual([r['id'] for r in data['items']], [1])
        self.assertEqual(data['total'], 1)

    def test_search_order_id_customer_and_sku_without_duplicate_orders(self):
        self.assertEqual(self.get('/search?keyword=%231')['orders'][0]['id'], 1)
        self.assertEqual(self.get('/search?keyword=甲')['order_total'], 2)
        self.assertEqual(self.get('/search?keyword=SKU-1')['order_total'], 2)
        self.assertEqual(self.get('/orders?keyword=物品')['total'], 3)
        self.assertEqual(self.get('/orders?keyword=物品')['items'][-1]['total'], '4.00')
        self.assertEqual(self.get('/search?keyword=物品')['product_total'], 24)
        self.assertEqual(len(self.get('/search?keyword=物品')['products']), 5)

    def test_search_treats_wildcards_and_sql_as_literal_text(self):
        for term in ['%25', '_', "%27%20OR%201=1--"]:
            data = self.get('/search?keyword=' + term)
            self.assertEqual((data['product_total'], data['order_total']), (0, 0))

    def test_model_exports_and_permissions(self):
        from backend.model_export import generate
        data=self.get('/model')
        self.assertEqual(len(data['tables']),8)
        self.assertEqual(self.client.post('/api/model/generate',headers=self.headers).status_code,403)
        self.assertEqual(self.client.get('/api/model').status_code,401)
        with self.app.app_context():
            headers={'Authorization':'Bearer '+issue_token({'id':1})}
        response=self.client.post('/api/model/generate',headers=headers)
        self.assertEqual(response.status_code,200)
        files=response.json['data']['files']
        self.assertEqual(len(files),3)
        self.assertIn('CREATE TABLE sales_order',files['schema_mysql.sql'])
        self.assertIn('erDiagram',files['model.mmd'])
        self.assertEqual(response.json['data']['version'],data['version'])

    def test_model_properties_and_cardinality(self):
        data = self.get('/model')
        tables = {t['name']: t for t in data['tables']}
        order = tables['sales_order']
        self.assertEqual(order['description'], '订单')
        self.assertTrue(all(c['description'] for c in order['columns']))
        self.assertEqual({i['kind'] for i in order['indexes']}, {'PRIMARY KEY', 'UNIQUE', 'INDEX'})
        stock_keys = [c for c in tables['stock']['columns'] if c['primary']]
        self.assertEqual(len(stock_keys), 2)
        self.assertTrue(all(c['references'] for c in stock_keys))
        from backend.model_export import generate
        mermaid = generate()['files']['model.mmd']
        self.assertIn('sales_order ||--o| shipment', mermaid)
        self.assertIn('product ||--o{ stock', mermaid)
        self.assertEqual(self.client.post('/api/model/validate').status_code, 401)
        result = self.client.post('/api/model/validate', headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json['data']['valid'])
        with patch('backend.model_export.CreateTable', side_effect=ValueError('bad model')):
            result = self.client.post('/api/model/validate', headers=self.headers)
        self.assertFalse(result.json['data']['valid'])
        self.assertTrue(result.json['data']['issues'])

    def test_validation_and_auth_fail_closed(self):
        for path in ['/inventory/summary', '/search?keyword=SKU', '/orders?status=pending', '/overview']:
            self.assertEqual(self.client.get('/api'+path).status_code, 401)
        for path in ['/search', '/search?keyword='+'a'*81, '/orders?status=unknown', '/overview?days=8', '/overview?days=0']:
            self.assertEqual(self.client.get('/api'+path, headers=self.headers).status_code, 422)

    @patch('backend.controllers.now', return_value=datetime(2026, 10, 23, 1))
    def test_overview_uses_shanghai_dates_and_counts_orders_once(self, _clock):
        with self.engine.begin() as c:
            c.execute(update(sales_order).where(sales_order.c.id == 1).values(created_at=datetime(2026, 10, 22, 15, 59)))
            c.execute(update(sales_order).where(sales_order.c.id == 2).values(created_at=datetime(2026, 10, 22, 16)))
            c.execute(insert(shipment).values(order_id=2, tracking_no='boundary', shipped_at=datetime(2026, 10, 22, 16)))
        data = self.get('/overview?days=7')
        self.assertEqual(data['order_count'], 3)  # Order 1 has two item rows.
        self.assertEqual(data['pending_count'], 1)
        self.assertEqual(data['shipped_today'], 1)
        self.assertEqual(data['available_quantity'], 649)
        self.assertEqual(data['timezone'], 'Asia/Shanghai')
        self.assertEqual(data['trend'][0]['date'], '2026-10-17')
        self.assertEqual(data['trend'][-2], {'date': '2026-10-22', 'created': 1, 'shipped': 0})
        self.assertEqual(data['trend'][-1], {'date': '2026-10-23', 'created': 1, 'shipped': 1})
        self.assertEqual(sum(w['order_count'] for w in data['warehouses']), 3)
        self.assertEqual(data['recent_orders'][-1]['total'], '4.00')

    def test_empty_overview_has_real_zero_counts_and_full_date_range(self):
        with self.engine.begin() as c:
            for table in reversed(metadata.sorted_tables):
                if table.name != 'account':
                    c.execute(delete(table))
        data = self.get('/overview?days=90')
        self.assertEqual(data['order_count'], 0)
        self.assertEqual(data['available_quantity'], 0)
        self.assertEqual(len(data['trend']), 90)
        self.assertTrue(all(r['created'] == r['shipped'] == 0 for r in data['trend']))
        self.assertEqual(data['recent_orders'], [])


if __name__ == '__main__':
    unittest.main()
