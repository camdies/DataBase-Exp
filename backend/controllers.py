"""库存锁定、订单事务和联表查询。无 HTTP 依赖；每个方法校验操作者。"""
from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select, func, case, and_, or_, insert, update, delete, literal_column
from .models import account, customer, product, warehouse, stock, sales_order, order_item, shipment
from .validation import Problem, integer, string, money, authorize


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InventoryController:
    def __init__(self, engine):
        self.engine = engine

    def references(self, actor, keyword=''):
        authorize(actor)
        with self.engine.connect() as c:
            customers = c.execute(select(customer.c.id, customer.c.name).where(
                customer.c.name.contains(keyword, autoescape=True)).order_by(customer.c.id).limit(50)).mappings().all()
            warehouses = c.execute(select(warehouse).order_by(warehouse.c.id)).mappings().all()
        return {'customers': [dict(x) for x in customers], 'warehouses': [dict(x) for x in warehouses]}

    def products(self, actor, keyword='', page=1):
        authorize(actor)
        condition = or_(product.c.name.contains(keyword, autoescape=True), product.c.sku.contains(keyword, autoescape=True))
        with self.engine.connect() as c:
            total = c.scalar(select(func.count()).select_from(product).where(condition))
            rows = c.execute(select(product).where(condition).order_by(product.c.id.desc()).offset((page-1)*20).limit(20)).mappings().all()
            ids = [x['id'] for x in rows]
            balances = c.execute(select(stock.c.product_id, stock.c.warehouse_id, warehouse.c.name, stock.c.quantity)
                                .join(warehouse).where(stock.c.product_id.in_(ids))).mappings().all() if ids else []
        return {'total': total, 'items': [dict(x, stocks=[dict(s) for s in balances if s['product_id'] == x['id']]) for x in rows]}

    def save_product(self, actor, payload, product_id=None):
        authorize(actor, admin=True)
        values = {'sku': string(payload.get('sku'), 'SKU', 40),
                  'name': string(payload.get('name'), '商品名称', 80), 'price': money(payload.get('price'))}
        with self.engine.begin() as c:
            if product_id:
                exists = c.scalar(select(product.c.id).where(product.c.id == product_id).with_for_update())
                if not exists:
                    raise Problem(404, 'NOT_FOUND', '商品不存在')
                c.execute(update(product).where(product.c.id == product_id).values(**values))
            else:
                product_id = c.execute(insert(product).values(**values)).inserted_primary_key[0]
                for wid in c.scalars(select(warehouse.c.id).order_by(warehouse.c.id)):
                    c.execute(insert(stock).values(warehouse_id=wid, product_id=product_id, quantity=0))
        return {'id': product_id}

    def delete_product(self, actor, product_id):
        authorize(actor, admin=True)
        with self.engine.begin() as c:
            if not c.scalar(select(product.c.id).where(product.c.id == product_id).with_for_update()):
                raise Problem(404, 'NOT_FOUND', '商品不存在')
            balances = c.execute(select(stock).where(stock.c.product_id == product_id)
                                 .order_by(stock.c.warehouse_id).with_for_update()).mappings().all()
            if any(x['quantity'] for x in balances) or c.scalar(select(order_item.c.order_id).where(order_item.c.product_id == product_id).limit(1)):
                raise Problem(409, 'PRODUCT_IN_USE', '商品有库存或历史订单，不能删除')
            c.execute(delete(stock).where(stock.c.product_id == product_id))
            c.execute(delete(product).where(product.c.id == product_id))
        return {'id': product_id}

    def restock(self, actor, payload):
        authorize(actor, admin=True)
        pid = integer(payload.get('product_id'), '商品')
        wid = integer(payload.get('warehouse_id'), '仓库')
        quantity = integer(payload.get('quantity'), '入库数量', maximum=1000000)
        with self.engine.begin() as c:
            # 和订单一致：商品 ID 升序 -> 库存，避免反向加锁。
            c.execute(select(product.c.id).where(product.c.id == pid).with_for_update()).first()
            current = c.scalar(select(stock.c.quantity).where(stock.c.product_id == pid, stock.c.warehouse_id == wid).with_for_update())
            if current is None:
                raise Problem(404, 'NOT_FOUND', '商品或仓库不存在')
            if current + quantity > 2147483647:
                raise Problem(409, 'STOCK_OVERFLOW', '库存数量超限')
            c.execute(update(stock).where(stock.c.product_id == pid, stock.c.warehouse_id == wid).values(quantity=current+quantity))
        return {'quantity': current+quantity}

    def create_order(self, actor, payload):
        authorize(actor)
        cid = integer(payload.get('customer_id'), '客户')
        wid = integer(payload.get('warehouse_id'), '仓库')
        try:
            key = str(UUID(payload.get('request_key', '')))
        except (ValueError, TypeError, AttributeError):
            raise Problem(422, 'INVALID_INPUT', 'request_key 必须为 UUID')
        raw = payload.get('items')
        if not isinstance(raw, list) or not 1 <= len(raw) <= 20 or any(not isinstance(x, dict) for x in raw):
            raise Problem(422, 'INVALID_INPUT', '订单需要 1–20 条明细')
        items = sorted([(integer(x.get('product_id'), '商品'), integer(x.get('quantity'), '数量', maximum=10000)) for x in raw])
        if len({x[0] for x in items}) != len(items):
            raise Problem(422, 'INVALID_INPUT', '同一商品请合并数量')
        with self.engine.begin() as c:
            if not c.scalar(select(customer.c.id).where(customer.c.id == cid)):
                raise Problem(404, 'NOT_FOUND', '客户不存在')
            if not c.scalar(select(warehouse.c.id).where(warehouse.c.id == wid)):
                raise Problem(404, 'NOT_FOUND', '仓库不存在')
            oid = c.execute(insert(sales_order).values(request_key=key, customer_id=cid, warehouse_id=wid,
                created_by=actor['id'], status='pending', created_at=now())).inserted_primary_key[0]
            for pid, qty in items:
                price = c.scalar(select(product.c.price).where(product.c.id == pid).with_for_update())
                balance = c.scalar(select(stock.c.quantity).where(stock.c.product_id == pid, stock.c.warehouse_id == wid).with_for_update())
                if price is None or balance is None:
                    raise Problem(404, 'NOT_FOUND', '商品或库存记录不存在')
                if balance < qty:
                    raise Problem(409, 'INSUFFICIENT_STOCK', f'商品 {pid} 库存不足，订单已回滚')
                c.execute(update(stock).where(stock.c.product_id == pid, stock.c.warehouse_id == wid).values(quantity=balance-qty))
                c.execute(insert(order_item).values(order_id=oid, product_id=pid, quantity=qty, unit_price=price))
        return {'id': oid}

    def orders(self, actor, page=1, customer_id=None, status=None, keyword=""):
        authorize(actor)
        if status not in (None, '', 'pending', 'shipped', 'cancelled'):
            raise Problem(422, 'INVALID_INPUT', '未知订单状态')
        base_condition = sales_order.c.customer_id == customer_id if customer_id else True
        if keyword:
            needle = keyword.lstrip('#')
            matches_product = select(order_item.c.order_id).join(product).where(or_(
                product.c.sku.contains(keyword, autoescape=True), product.c.name.contains(keyword, autoescape=True)))
            matches_customer = select(customer.c.id).where(customer.c.name.contains(keyword, autoescape=True))
            base_condition = and_(base_condition, or_(
                sales_order.c.id == int(needle) if needle.isascii() and needle.isdigit() and len(needle)<=10 else False,
                sales_order.c.customer_id.in_(matches_customer), sales_order.c.id.in_(matches_product)))
        condition = and_(base_condition, sales_order.c.status == status) if status else base_condition
        totals = select(order_item.c.order_id, func.sum(order_item.c.quantity*order_item.c.unit_price).label('total')).group_by(order_item.c.order_id).subquery()
        joined = sales_order.join(customer).join(warehouse).join(account).join(
            totals, totals.c.order_id == sales_order.c.id).outerjoin(shipment)
        query = select(sales_order, customer.c.name.label('customer_name'), warehouse.c.name.label('warehouse_name'),
            account.c.username.label('operator'), totals.c.total, shipment.c.tracking_no).select_from(joined).where(condition)
        with self.engine.connect() as c:
            counts = dict.fromkeys(['pending', 'shipped', 'cancelled'], 0)
            counts.update(dict(c.execute(select(sales_order.c.status, func.count()).where(base_condition).group_by(sales_order.c.status)).all()))
            counts['all'] = sum(counts.values())
            total = counts[status] if status else counts['all']
            rows = c.execute(query.order_by(sales_order.c.id.desc()).offset((page-1)*20).limit(20)).mappings().all()
        return {'total': total, 'items': [dict(r) for r in rows], 'counts': counts}

    def inventory_summary(self, actor):
        authorize(actor)
        balances = select(product.c.id, func.coalesce(func.sum(stock.c.quantity), 0).label('quantity')).select_from(
            product.outerjoin(stock)).group_by(product.c.id).subquery()
        with self.engine.connect() as c:
            row = c.execute(select(func.count().label('product_count'),
                func.coalesce(func.sum(balances.c.quantity), 0).label('available_quantity'),
                func.coalesce(func.sum(case((balances.c.quantity < 10, 1), else_=0)), 0).label('low_stock_count')).select_from(balances)).mappings().one()
            warehouse_count = c.scalar(select(func.count()).select_from(warehouse))
        return {**{key: int(value) for key, value in row.items()}, 'warehouse_count': warehouse_count}

    def search(self, actor, keyword):
        authorize(actor)
        keyword = string(keyword, '搜索词', 80)
        products = self.products(actor, keyword)
        orders = self.orders(actor, keyword=keyword)
        customers = self.references(actor, keyword)['customers']
        return {'products': products['items'][:5], 'orders': orders['items'][:5],
                'customers': customers[:5], 'product_total': products['total'], 'order_total': orders['total']}

    def overview(self, actor, days=30):
        """One read snapshot; Shanghai calendar dates with UTC storage, no business writes."""
        authorize(actor)
        if days not in (7, 30, 90):
            raise Problem(422, 'INVALID_INPUT', '趋势范围仅支持 7、30、90 天')
        generated = now()
        today = (generated + timedelta(hours=8)).date()
        first = today - timedelta(days=days-1)
        start = datetime.combine(first, datetime.min.time()) - timedelta(hours=8)
        end = datetime.combine(today + timedelta(days=1), datetime.min.time()) - timedelta(hours=8)
        today_start = end - timedelta(days=1)
        trend = {str(first + timedelta(days=i)): {'date': str(first + timedelta(days=i)), 'created': 0, 'shipped': 0} for i in range(days)}
        def business_date(column):
            if self.engine.dialect.name == 'sqlite':
                return func.date(column, '+8 hours')
            return func.date(func.timestampadd(literal_column('HOUR'), 8, column))
        with self.engine.connect() as connection:
            c = connection.execution_options(isolation_level='REPEATABLE READ') if self.engine.dialect.name == 'mysql' else connection
            with c.begin():
                counts = dict.fromkeys(['pending', 'shipped', 'cancelled'], 0)
                counts.update(dict(c.execute(select(sales_order.c.status, func.count()).group_by(sales_order.c.status)).all()))
                order_count = sum(counts.values())
                shipped_today = c.scalar(select(func.count()).select_from(shipment).where(shipment.c.shipped_at >= today_start, shipment.c.shipped_at < end))
                available = c.scalar(select(func.coalesce(func.sum(stock.c.quantity), 0)))
                for table, column, key in [(sales_order, sales_order.c.created_at, 'created'), (shipment, shipment.c.shipped_at, 'shipped')]:
                    bucket = business_date(column)
                    for date, count in c.execute(select(bucket, func.count()).select_from(table).where(column >= start, column < end).group_by(bucket)):
                        trend[str(date)][key] = count
                warehouses = [dict(row) for row in c.execute(select(warehouse.c.id, warehouse.c.name, func.count(sales_order.c.id).label('order_count')).select_from(
                    warehouse.outerjoin(sales_order)).group_by(warehouse.c.id, warehouse.c.name).order_by(warehouse.c.id)).mappings()]
                totals = select(order_item.c.order_id, func.sum(order_item.c.quantity * order_item.c.unit_price).label('total')).group_by(order_item.c.order_id).subquery()
                recent = [dict(row) for row in c.execute(select(sales_order.c.id, sales_order.c.status, sales_order.c.created_at,
                    customer.c.name.label('customer_name'), warehouse.c.name.label('warehouse_name'), totals.c.total).select_from(
                    sales_order.join(customer).join(warehouse).join(totals, totals.c.order_id == sales_order.c.id)).order_by(sales_order.c.id.desc()).limit(6)).mappings()]
        return {'order_count': order_count, 'shipped_today': shipped_today, 'available_quantity': int(available),
                'pending_count': counts['pending'], 'status_counts': counts, 'trend': list(trend.values()),
                'warehouses': warehouses, 'recent_orders': recent, 'generated_at': generated, 'timezone': 'Asia/Shanghai', 'days': days}

    def detail(self, actor, oid):
        authorize(actor)
        with self.engine.connect() as c:
            if not c.scalar(select(sales_order.c.id).where(sales_order.c.id == oid)):
                raise Problem(404, 'NOT_FOUND', '订单不存在')
            rows = c.execute(select(order_item, product.c.sku, product.c.name).join(product).where(order_item.c.order_id == oid)).mappings().all()
        return [dict(x) for x in rows]

    def transition(self, actor, oid, action, payload):
        authorize(actor)
        with self.engine.begin() as c:
            order = c.execute(select(sales_order).where(sales_order.c.id == oid).with_for_update()).mappings().first()
            if not order:
                raise Problem(404, 'NOT_FOUND', '订单不存在')
            if order['status'] != 'pending':
                raise Problem(409, 'INVALID_STATE', '只有待发货订单可以发货或取消')
            if action == 'ship':
                tracking = string(payload.get('tracking_no'), '物流单号', 60)
                c.execute(insert(shipment).values(order_id=oid, tracking_no=tracking, shipped_at=now()))
                status = 'shipped'
            elif action == 'cancel':
                items = c.execute(select(order_item).where(order_item.c.order_id == oid).order_by(order_item.c.product_id)).mappings().all()
                for item in items:
                    pid = item['product_id']
                    c.execute(select(product.c.id).where(product.c.id == pid).with_for_update()).first()
                    balance = c.scalar(select(stock.c.quantity).where(stock.c.product_id == pid, stock.c.warehouse_id == order['warehouse_id']).with_for_update())
                    if balance is None or balance + item['quantity'] > 2147483647:
                        raise Problem(409, 'STOCK_CONFLICT', '库存异常，取消已回滚')
                    c.execute(update(stock).where(stock.c.product_id == pid, stock.c.warehouse_id == order['warehouse_id']).values(quantity=balance+item['quantity']))
                status = 'cancelled'
            else:
                raise Problem(422, 'INVALID_INPUT', '未知订单操作')
            c.execute(update(sales_order).where(sales_order.c.id == oid).values(status=status))
        return {'id': oid, 'status': status}
