"""可执行关系模型：DDL 和 ER 图均从此处生成。金额采用定点数。"""
from sqlalchemy import (MetaData, Table, Column, Integer, String, Numeric, DateTime,
                        ForeignKey, CheckConstraint, Index, UniqueConstraint)

metadata = MetaData()

account = Table('account', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', String(40), nullable=False, unique=True),
    Column('password_hash', String(60), nullable=False),
    Column('role', String(10), nullable=False),
    CheckConstraint("role IN ('admin','clerk')", name='ck_account_role'))
customer = Table('customer', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(80), nullable=False),
    Column('phone', String(30), nullable=False),
    Column('address', String(200), nullable=False))
product = Table('product', metadata,
    Column('id', Integer, primary_key=True),
    Column('sku', String(40), nullable=False, unique=True),
    Column('name', String(80), nullable=False),
    Column('price', Numeric(10, 2), nullable=False),
    CheckConstraint('price > 0', name='ck_product_price'))
warehouse = Table('warehouse', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(80), nullable=False, unique=True))
stock = Table('stock', metadata,
    Column('warehouse_id', Integer, ForeignKey('warehouse.id'), primary_key=True),
    Column('product_id', Integer, ForeignKey('product.id'), primary_key=True),
    Column('quantity', Integer, nullable=False),
    CheckConstraint('quantity >= 0', name='ck_stock_quantity'))
sales_order = Table('sales_order', metadata,
    Column('id', Integer, primary_key=True),
    Column('request_key', String(36), nullable=False, unique=True),
    Column('customer_id', Integer, ForeignKey('customer.id'), nullable=False),
    Column('warehouse_id', Integer, ForeignKey('warehouse.id'), nullable=False),
    Column('created_by', Integer, ForeignKey('account.id'), nullable=False),
    Column('status', String(12), nullable=False),
    Column('created_at', DateTime, nullable=False),
    CheckConstraint("status IN ('pending','shipped','cancelled')", name='ck_order_status'))
Index('ix_order_customer_created', sales_order.c.customer_id, sales_order.c.created_at)
order_item = Table('order_item', metadata,
    Column('order_id', Integer, ForeignKey('sales_order.id'), primary_key=True),
    Column('product_id', Integer, ForeignKey('product.id'), primary_key=True),
    Column('quantity', Integer, nullable=False),
    Column('unit_price', Numeric(10, 2), nullable=False),
    CheckConstraint('quantity > 0 AND unit_price > 0', name='ck_item_value'))
shipment = Table('shipment', metadata,
    Column('order_id', Integer, ForeignKey('sales_order.id'), primary_key=True),
    Column('tracking_no', String(60), nullable=False, unique=True),
    Column('shipped_at', DateTime, nullable=False))

for table in metadata.tables.values():
    table.dialect_options['mysql']['engine'] = 'InnoDB'
    table.dialect_options['mysql']['charset'] = 'utf8mb4'
