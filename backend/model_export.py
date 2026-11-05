"""Read-only metadata serialization and in-memory DDL generation."""
import hashlib
import json
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import mysql, mssql
from .models import metadata


TABLE_LABELS = dict(account='账号', customer='客户', product='商品', warehouse='仓库', stock='分仓库存', sales_order='订单', order_item='订单明细', shipment='发货')
FIELD_LABELS = dict(id='编号', username='用户名', password_hash='密码哈希', role='角色', name='名称', phone='电话', address='地址', sku='商品编号', price='单价', warehouse_id='仓库编号', product_id='商品编号', quantity='数量', request_key='幂等请求标识', customer_id='客户编号', created_by='操作员编号', status='订单状态', created_at='下单时间', order_id='订单编号', unit_price='成交单价', tracking_no='物流单号', shipped_at='发货时间')


def model():
    tables = []
    for t in metadata.sorted_tables:
        unique = [list(c.columns.keys()) for c in t.constraints if isinstance(c, UniqueConstraint)]
        indexes = [{'name': i.name, 'columns': list(i.columns.keys()), 'unique': i.unique, 'kind': 'UNIQUE' if i.unique else 'INDEX'} for i in sorted(t.indexes, key=lambda i: i.name)]
        indexes += [{'name': t.primary_key.name or '主键（未命名）', 'columns': list(t.primary_key.columns.keys()), 'unique': True, 'kind': 'PRIMARY KEY'}]
        indexes += [{'name': c.name or '唯一约束（未命名）', 'columns': list(c.columns.keys()), 'unique': True, 'kind': 'UNIQUE'} for c in t.constraints if isinstance(c, UniqueConstraint)]
        tables.append({'name': t.name, 'description': TABLE_LABELS.get(t.name, ''), 'columns': [{'name': c.name, 'description': FIELD_LABELS.get(c.name, ''), 'type': str(c.type), 'nullable': c.nullable, 'primary': c.primary_key, 'unique': [c.name] in unique, 'references': sorted(f.target_fullname for f in c.foreign_keys)} for c in t.columns], 'indexes': sorted(indexes, key=lambda i: (i['kind'], i['name'], i['columns'])), 'constraints': sorted(str(c.sqltext) for c in t.constraints if hasattr(c, 'sqltext'))})
    digest = hashlib.sha256(json.dumps(tables, sort_keys=True).encode()).hexdigest()[:16]
    return {'tables': tables, 'version': digest}


def validate():
    issues = []
    for t in metadata.sorted_tables:
        if not len(t.primary_key.columns):
            issues.append(t.name + ': 缺少主键')
        for c in t.columns:
            for fk in c.foreign_keys:
                try:
                    fk.column
                except Exception:
                    issues.append(t.name + '.' + c.name + ': 外键目标无法解析')
    for name, dialect in [('MySQL', mysql.dialect()), ('SQL Server', mssql.dialect())]:
        for t in metadata.sorted_tables:
            try:
                str(CreateTable(t).compile(dialect=dialect))
                for index in t.indexes:
                    str(CreateIndex(index).compile(dialect=dialect))
            except Exception:
                issues.append(name + ': ' + t.name + ' 编译失败')
    return {'valid': not issues, 'issues': issues, 'version': model()['version'], 'checks': ['主键存在', '外键目标解析', 'MySQL / SQL Server 建表及索引编译'], 'scope': '仅校验当前元数据与编译结果，不验证实际数据库、数据内容或第三范式。'}


def generate():
    files={}
    for name,dialect in [('mysql',mysql.dialect()),('sqlserver',mssql.dialect())]:
        statements=['-- Generated from current metadata. Run only in a NEW empty database.']
        for t in metadata.sorted_tables:
            statements.append(str(CreateTable(t).compile(dialect=dialect)).strip()+';')
            statements.extend(str(CreateIndex(i).compile(dialect=dialect)).strip()+';' for i in sorted(t.indexes,key=lambda i:i.name))
        files['schema_'+name+'.sql']='\n\n'.join(statements)+'\n'
    lines=['erDiagram']
    for t in metadata.sorted_tables:
        lines.append('    '+t.name+' {')
        for c in t.columns:
            keys=([ 'PK' ] if c.primary_key else [])+(['FK'] if c.foreign_keys else [])+(['UK'] if c.unique else [])
            lines.append('        '+str(c.type).split('(')[0].lower()+' '+c.name+(' '+','.join(keys) if keys else ''))
        lines.append('    }')
        for c in t.columns:
            for fk in c.foreign_keys:
                one=c.unique or (c.primary_key and len(t.primary_key.columns)==1)
                lines.append('    '+fk.column.table.name+' ||--'+('o|' if one else 'o{')+' '+t.name+' : '+c.name)
    files['model.mmd']='\n'.join(lines)+'\n'
    return {'files':files,'version':model()['version']}
