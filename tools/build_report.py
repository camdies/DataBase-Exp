"""根据真实 evidence 生成课程报告。需要 reportlab；与服务运行依赖分离。"""
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, Flowable
from reportlab.graphics.shapes import Drawing, Rect, Line, String

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / 'doument'
EVIDENCE = DOC / 'evidence'
font_path = Path(os.getenv('REPORT_FONT', 'C:/Windows/Fonts/msyh.ttc'))
if font_path.exists():
    pdfmetrics.registerFont(TTFont('ReportCJK', str(font_path), subfontIndex=0))
    FONT = 'ReportCJK'
else:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    FONT = 'STSong-Light'
BLUE = colors.HexColor('#2563eb')
INK = colors.HexColor('#1f2937')
MUTED = colors.HexColor('#6b7280')
styles = {
    'title':ParagraphStyle('title',fontName=FONT,fontSize=30,leading=42,textColor=INK,spaceAfter=18),
    'h1':ParagraphStyle('h1',fontName=FONT,fontSize=22,leading=30,textColor=INK,spaceAfter=18),
    'h2':ParagraphStyle('h2',fontName=FONT,fontSize=13,leading=19,textColor=BLUE,spaceBefore=10,spaceAfter=8),
    'body':ParagraphStyle('body',fontName=FONT,fontSize=10,leading=17,textColor=INK,spaceAfter=9,wordWrap='CJK'),
    'small':ParagraphStyle('small',fontName=FONT,fontSize=8.5,leading=13,textColor=MUTED,spaceAfter=7,wordWrap='CJK'),
    'code':ParagraphStyle('code',fontName='Courier',fontSize=8,leading=12,textColor=INK,backColor=colors.HexColor('#f1f5f9'),borderPadding=9,spaceBefore=5,spaceAfter=12),
}
story=[]
def p(text, style='body'):
    return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
def add(text,style='body'): story.append(p(text,style))
def code(text): story.append(Paragraph(escape(text).replace(' ','&nbsp;').replace('\n','<br/>'),styles['code']))
def heading(number,title):
    if story: story.append(PageBreak())
    add(f'{number:02} / DATABASE COURSEWORK','small');add(title,'h1')
def table(headers,rows,widths):
    data=[[p(x,'small') for x in headers]]+[[p(x,'small') for x in row] for row in rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eff6ff')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#bfdbfe')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#e5e7eb')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(t);story.append(Spacer(1,10))
def load(name): return json.loads((EVIDENCE/name).read_text(encoding='utf-8'))


def erd():
    d=Drawing(505,515)
    boxes={
        'account':(0,390,145,100,['PK id','UK username','password_hash','role']),
        'customer':(0,205,145,100,['PK id','name','phone','address']),
        'warehouse':(0,30,145,70,['PK id','UK name']),
        'sales_order':(175,185,150,155,['PK id','UK request_key','FK customer_id','FK warehouse_id','FK created_by','status','created_at']),
        'shipment':(175,400,150,90,['PK/FK order_id','UK tracking_no','shipped_at']),
        'order_item':(355,205,150,100,['PK/FK order_id','PK/FK product_id','quantity','unit_price']),
        'product':(355,390,150,100,['PK id','UK sku','name','price']),
        'stock':(355,30,150,90,['PK/FK warehouse_id','PK/FK product_id','quantity']),
    }
    def line(points,label,lx,ly):
        for a,b in zip(points,points[1:]): d.add(Line(*a,*b,strokeColor=colors.HexColor('#94a3b8'),strokeWidth=.9))
        d.add(String(lx,ly,label,fontName='Helvetica',fontSize=8,fillColor=BLUE))
    line([(145,430),(160,430),(160,325),(175,325)],'1:N',148,365)
    line([(145,255),(175,255)],'1:N',146,264)
    line([(145,65),(245,65),(245,185)],'1:N',220,137)
    line([(245,340),(245,400)],'1:0..1',253,366)
    line([(325,250),(355,250)],'1:N',326,262)
    line([(430,305),(430,390)],'N:1',439,346)
    line([(145,48),(355,48)],'1:N',267,57)
    line([(485,120),(495,145),(515,145),(515,440),(505,440)],'N:1',471,163)
    for name,(x,y,w,h,fields) in boxes.items():
        d.add(Rect(x,y,w,h,fillColor=colors.white,strokeColor=colors.HexColor('#cbd5e1'),strokeWidth=.7,rx=5))
        d.add(Rect(x,y+h-24,w,24,fillColor=colors.HexColor('#eff6ff'),strokeColor=None))
        d.add(String(x+8,y+h-16,name,fontName='Helvetica-Bold',fontSize=10,fillColor=INK))
        for i,f in enumerate(fields): d.add(String(x+8,y+h-40-i*15,f,fontName='Helvetica',fontSize=8.6,fillColor=INK))
    return d


def build():
    counts=load('initial_counts.json'); idx=load('index-demo.json'); win=load('concurrency/summary.json'); net=load('network/summary.json'); native=load('windows-server/summary.json'); single=load('single-user/summary.json')
    story.append(Spacer(1,35));add('课程作业 1 · 关系型数据库应用','small')
    add('序仓\n企业订单与库存管理','title')
    add('基于 Python / Web / MySQL 的数据库访问实践','h2')
    add(f"学号：{os.getenv('STUDENT_ID','________________')}    姓名：{os.getenv('STUDENT_NAME','________________')}\n班级：{os.getenv('STUDENT_CLASS','________________')}    课程：数据库系统原理\n验证日期：2026年10月11日")
    story.append(Spacer(1,20))
    table(['8 张关系表','106,005 条初始数据','2 个业务页面'],[['事务 + 行锁 + 外键','真实备份与恢复校验','订单履约 / 商品库存']],[170,170,170])
    add('项目摘要','h2')
    add('面向中小企业多仓履约场景，系统维护客户、商品、仓库、分仓库存、订单、明细、物流与操作账户。业务围绕下单扣库、发货和取消返库展开；使用关系约束与事务维持数据一致性，通过索引与多客户端访问实验观察查询性能。')
    add('本次从既有教务项目保留 Vue 3、Element Plus、Pinia、Flask、SQLAlchemy 技术栈与浅色视觉令牌，重新实现企业业务；不沿用选课、成绩、审核、嵌入式 Python 或便携数据库分发。')
    add('交付内容','h2')
    add('data：自动生成的 MySQL 建表脚本、SQL Server 模型参考、ERD 模型和真实数据备份。\ncode：分层后端、两个业务页、数据库实验、真实 MySQL 测试与已构建前端。\ndoument：本报告、部署验收说明、测试结果、请求耗时原始数据、浏览器截图。')
    add('报告中性能与测试数据来自随附 evidence 文件；学号和姓名尚未提供，提交前必须补全。','small')

    heading(1,'需求对照与业务范围')
    table(['课程要求','具体实现 / 证据'],[
        ['传统数据库与轻量服务','MySQL 8 / PyMySQL / SQLAlchemy Core / Flask；浏览器访问 REST API'],
        ['创建与删除数据表','schema_mysql.sql；tools.manage ddl-demo 的专用实验表完整生命周期'],
        ['插入、修改、删除、JOIN','商品 CRUD、入库、订单事务；订单列表联查客户、仓库、账户、金额、物流'],
        ['事务支持','下单与取消均 engine.begin；库存行锁；异常自动回滚'],
        ['索引支持','唯一键、复合主键、订单客户时间索引；EXPLAIN 与30轮实测'],
        ['多用户并发与性能','多账号管理、8客户端并发；四组共1000请求；持续JSONL日志与CSV逐条匹配'],
        ['5-10实体 / ≥100000行','8表 / 106005行；计数及独立库恢复 CHECKSUM 一致'],
        ['1:1、1:N、N:M联系','订单-物流；客户-订单；订单-商品 / 仓库-商品'],
        ['建模与代码生成','SQLAlchemy 可执行模型 → MySQL/SQL Server DDL + Mermaid ERD'],
        ['Linux服务端 / 网络访问','Ubuntu MySQL/Gunicorn与Windows原生MySQL/Waitress；独立IP实测'],
        ['1-2业务页 / RAR<100MB','订单履约与商品库存；排除依赖目录、运行时及数据库物理文件'],
    ],[150,360])
    add('权限与范围','h2')
    add('管理员管理商品、入库与所有订单；业务员共享企业订单的创建、查询、发货和取消权限，只读商品与库存。共享范围是企业内部显式授权，不把操作员字段当作私人订单归属。系统不包含支付、采购审批、库存流水或公网用户注册。')
    add('流程','h2')
    add('维护商品 → 管理员入库 → 业务员选择客户、仓库与明细 → 原子下单扣库 → 发货创建物流记录，或取消返库。已发货 / 已取消订单不能再次转换。')

    heading(2,'实体关系与基数约束')
    story.append(erd())
    add('图例：PK 主键；FK 外键；UK 唯一键。完整可编辑模型：data/model.mmd。','small')
    add('订单与物流是 1:0..1：待发货订单没有物流，已发货订单恰有一条；shipment.order_id 同时是主键和外键，结构上保证最多一条。订单必须有至少一条明细由业务事务保证。')
    add('订单与商品通过 order_item 构成多对多；仓库与商品通过 stock 构成多对多。联合主键禁止同一订单重复商品、同一仓库重复商品库存行。')

    heading(3,'关系模式与数据字典')
    table(['关系 / 主键','属性类型与外键','数据量'],[
      ['account\nPK id','id INT；username VARCHAR(40) UNIQUE；password_hash VARCHAR(60)；role VARCHAR(10)',counts['account']],
      ['customer\nPK id','id INT；name VARCHAR(80)；phone VARCHAR(30)；address VARCHAR(200)',counts['customer']],
      ['product\nPK id','id INT；sku VARCHAR(40) UNIQUE；name VARCHAR(80)；price DECIMAL(10,2)>0',counts['product']],
      ['warehouse\nPK id','id INT；name VARCHAR(80) UNIQUE',counts['warehouse']],
      ['stock\nPK (warehouse_id,product_id)','warehouse_id→warehouse.id；product_id→product.id；quantity INT≥0',counts['stock']],
      ['sales_order\nPK id','request_key VARCHAR(36) UNIQUE；customer_id→customer.id；warehouse_id→warehouse.id；created_by→account.id；status VARCHAR(12)；created_at DATETIME',counts['sales_order']],
      ['order_item\nPK (order_id,product_id)','order_id→sales_order.id；product_id→product.id；quantity INT>0；unit_price DECIMAL(10,2)>0',counts['order_item']],
      ['shipment\nPK order_id','order_id→sales_order.id；tracking_no VARCHAR(60) UNIQUE；shipped_at DATETIME',counts['shipment']],
    ],[135,310,65])
    add('所有业务字段均 NOT NULL。单列 id 使用自增；复合主键及 shipment.order_id 不自增。MySQL 使用 InnoDB 与 utf8mb4。外键默认限制被引用记录删除，不级联抹去历史。')
    add('初始数据口径','h2')
    add('2000个模拟企业客户、1000种商品、3个仓库、3000条库存、25000笔历史订单及50000条明细、25000条物流、2个账户。总计106005。客户电话均为 TEST 标记，不是真实号码。库存5000为导入时点结余，历史已履约订单不再重复扣库。')

    heading(4,'规范化、完整性与安全边界')
    add('第三范式检查','h2')
    table(['关系组','函数依赖与分解理由'],[
        ['客户 / 商品 / 仓库 / 账户','id决定全部非键属性；SKU、用户名、仓库名作为候选键。订单不复制客户地址、商品现价或操作员名称，避免传递依赖。'],
        ['stock','(warehouse_id, product_id) → quantity；数量依赖完整复合键，不依赖单一商品或仓库，满足2NF；无非键决定非键，满足3NF。'],
        ['order_item','(order_id, product_id) → quantity, unit_price。unit_price是该笔交易的成交价，不是商品现价，因此依赖整个明细键。'],
        ['sales_order / shipment','订单ID决定客户、仓库、操作员、状态、时间；物流独立为1:1扩展。总金额通过SUM明细计算，不存储可派生冗余字段。'],
    ],[135,375])
    add('约束与异常','h2')
    add('数量、价格由 CHECK 保证基本范围；状态使用有限字符串；FK、UNIQUE、PK负责跨调用者一致性。业务层验证状态流、库存充足、明细非空与角色。错误不会转成“成功但没有数据”。删除商品前必须零库存且无任何订单引用，否则409。')
    add('账户与查询','h2')
    add('bcrypt共享帮助函数默认12轮；JWT密钥只从环境读取且启动验证强度。受保护路由同时使用 require_auth 和 require_role；控制器也验证操作者。SQLAlchemy表达式及text绑定参数处理输入，表名与实验索引名固定，不拼接用户SQL。浏览器通过Vue文本插值展示数据，不使用v-html。')
    add('应用账号只授予 SELECT/INSERT/UPDATE/DELETE；DDL由管理命令和管理账号执行。数据库仅本机监听；公开网络部署需要额外TLS、限流与服务端会话撤销，这些不属于本次局域网课程实现。')

    heading(5,'实践一：SQL 基本操作与 JOIN')
    add('目标：用轻量服务组件完成六项基本操作。以下为实验执行的SQL与业务查询的等价形式；参数均由驱动绑定。')
    code('CREATE TABLE course_ddl_demo (\n  id INT PRIMARY KEY, note VARCHAR(80) NOT NULL\n) ENGINE=InnoDB;\nINSERT INTO course_ddl_demo VALUES (:id, :note);\nUPDATE course_ddl_demo SET note=:note WHERE id=:id;\nSELECT note FROM course_ddl_demo WHERE id=:id;\nDELETE FROM course_ddl_demo WHERE id=:id;\nDROP TABLE course_ddl_demo;')
    add('tools/manage.py 的 ddl_demo 查询并断言修改值为“已修改”、删除后COUNT=0、DROP后information_schema中没有实验表。已有同名实验表时拒绝覆盖。MySQL的DDL会隐式提交，因此实验与业务DML事务分开。')
    add('跨表业务查询','h2')
    code('SELECT o.id, c.name, w.name, a.username,\n       SUM(i.quantity * i.unit_price) AS total\nFROM sales_order o\nJOIN customer c ON c.id=o.customer_id\nJOIN warehouse w ON w.id=o.warehouse_id\nJOIN account a ON a.id=o.created_by\nJOIN order_item i ON i.order_id=o.id\nWHERE o.customer_id=:customer_id\nGROUP BY o.id, c.name, w.name, a.username;')
    add('实际列表在控制器中先按order_id聚合明细为子查询，再连接订单、客户、仓库、账户，并LEFT JOIN物流；待发货订单也可显示。每页20条，查询与COUNT使用一致客户条件。价格使用Decimal而不是二进制浮点；JSON金额以字符串传输。')
    add('网页对应：商品页新增/修改/删除；订单页按客户筛选并点击订单号查看明细。实验结果：evidence/ddl-demo.json。','small')

    heading(6,'实践二：事务、回滚与库存竞争')
    add('目标：多张表写入要么全部生效，要么全部撤销；两个客户端同时下单时不能超卖。')
    code('with engine.begin() as c:\n    # INSERT sales_order; request_key has a UNIQUE key\n    for product_id, quantity in sorted(items):\n        # SELECT product ... FOR UPDATE\n        # SELECT stock ... FOR UPDATE\n        if stock_quantity < quantity:\n            raise Problem(409, "INSUFFICIENT_STOCK", ...)\n        # UPDATE stock SET quantity=stock_quantity-quantity\n        # INSERT order_item with current unit_price\n# commit on success; rollback on exception')
    add('事务边界覆盖订单、每条明细和库存更新。商品按ID升序加锁；每个商品之后锁定对应分仓库存。取消先锁订单并确认pending，再以相同商品顺序返库。发货先锁订单，再写唯一物流记录并修改状态。')
    table(['ACID','具体保证'],[
        ['原子性','engine.begin异常回滚；第二条明细库存不足时首条扣库和订单头同时撤销。'],
        ['一致性','外键、唯一键、CHECK与业务规则共同维护状态、数量和关系。'],
        ['隔离性','READ COMMITTED + SELECT FOR UPDATE串行化冲突库存；真实MySQL竞争测试验证。'],
        ['持久性','MySQL InnoDB提交持久化；本报告没有进行断电恢复实验。'],
    ],[90,420])
    add('关键验证','h2')
    add('库存=1时两个独立连接同时购买1件：恰有一个成功，另一个收到库存不足，最终库存=0。两个客户端同时取消同一订单：恰有一次返库，另一次状态冲突。重复request_key返回409且不再次扣库；锁超时/死锁返回可识别冲突，不自动重试未知结果的写操作。')

    heading(7,'实践三：索引设计与性能比较')
    code('CREATE INDEX ix_order_customer_created\nON sales_order (customer_id, created_at);\n\nEXPLAIN SELECT id, created_at FROM sales_order\nFORCE INDEX (ix_order_customer_created)\nWHERE customer_id=:cid ORDER BY created_at;')
    add('复合索引先定位客户，再按时间有序读取；查询只需要id与created_at，InnoDB二级索引叶子包含主键，可形成覆盖索引。比较时仅用IGNORE INDEX禁用该索引，不删除业务索引。')
    no,yes=idx['without_index'],idx['with_index']
    table(['条件','访问类型 / 估计扫描行','中位耗时 / 返回行'],[
        ['IGNORE INDEX',f"{no['plan'][0]['type']} / {no['plan'][0]['rows']}",f"{no['median_ms']:.3f} ms / {no['rows']}"],
        ['FORCE INDEX',f"{yes['plan'][0]['type']} / {yes['plan'][0]['rows']}",f"{yes['median_ms']:.3f} ms / {yes['rows']}"],
    ],[155,175,180])
    add(f"同一客户42、同一连接、热缓存、各30轮；中位耗时比值约{no['median_ms']/yes['median_ms']:.1f}倍。两种方法返回的13行记录完全一致。EXPLAIN rows是优化器估算，不是实际结果条数；小表、不同硬件或负载可能得到不同结果。")
    add('代价与边界','h2')
    add('索引占磁盘空间并增加插入、更新成本；不能为所有字段无差别加索引。复合索引遵循最左前缀原则，不直接加速只按created_at且不带客户条件的全部查询。模糊商品名称采用包含匹配，本课程规模可接受，不声称可利用普通B树完成任意子串索引检索。')
    add('原始证据包含完整EXPLAIN、30个逐次耗时与结果条数：doument/evidence/index-demo.json。实验命令：python -m tools.manage index-demo。','small')

    heading(8,'实践四：Linux 部署与多客户端访问')
    add('运行拓扑','h2')
    add('Windows 浏览器 → localhost转发 → Ubuntu WSL中的Gunicorn与MySQL。由于当前WSL是mirrored模式，Windows与Linux共享主机网络地址；这一预览不冒充独立IP浏览器实验。另用Linux网络命名空间模拟独立客户端，进行真实TCP/HTTP访问。')
    table(['实验角色','地址 / 进程'],[['独立网络客户端','course-client namespace：172.29.241.2/30；8个并发HTTP客户端，2个账户'],['Linux服务端','临时veth：172.29.241.1/30；Gunicorn 2 workers × 4 threads，端口5001'],['数据库','同Linux服务器，MySQL 8.0，端口3306仅本地；应用账号最小DML权限']],[130,380])
    add('独立IP实验使用同一台WSL内的两个网络栈，不等于两台物理主机。tools/network_demo.sh 保存双方接口JSON，退出时删除临时接口，不改默认路由和防火墙。课堂若要求Windows实体机到Linux独立虚拟机，应依部署说明采用桥接VM，并重新记录现场结果。')
    table(['指标','Windows → WSL转发','独立IP HTTP'],[
        ['客户端数 / 账户数','8 / 2','8 / 2'],['请求成功 / 失败',f"{win['successful']} / {win['failed']}",f"{net['successful']} / {net['failed']}"],
        ['吞吐（次/秒）',f"{win['throughput_rps']:.2f}",f"{net['throughput_rps']:.2f}"],['P50 / P95（ms）',f"{win['p50_ms']:.2f} / {win['p95_ms']:.2f}",f"{net['p50_ms']:.2f} / {net['p95_ms']:.2f}"],
        ['最大耗时（ms）',f"{win['max_ms']:.2f}",f"{net['max_ms']:.2f}"],
    ],[160,175,175])
    add('负载：一半按客户跨表查询订单，一半查询商品及分仓库存。每客户端独立登录后同步开始，登录不计入性能统计。CSV记录client/user/path/status/latency/request_id；失败返回非零退出码。结果仅说明本机此负载，不能推断生产容量。')

    heading(9,'实践五：跨系统运行与持续日志')
    table(['实测环境','请求成功 / 失败','P95 / 吞吐'],[
        ['Windows原生MySQL 8.0 + Waitress；8客户端',f"{native['successful']} / {native['failed']}",f"{native['p95_ms']:.2f}ms / {native['throughput_rps']:.2f}次/秒"],
        ['Windows单机；1客户端',f"{single['successful']} / {single['failed']}",f"{single['p95_ms']:.2f}ms / {single['throughput_rps']:.2f}次/秒"],
    ],[230,115,165])
    add('Windows本机验证使用隔离的MySQL 8.0.46实例（127.0.0.1:3307），从交付脚本和备份恢复106005行，再运行17项测试和HTTP并发。验证结束停止临时进程；不修改旧教务数据库。Linux同样17项测试通过。')
    add('持续访问记录','h2')
    add('Python标准logging写入按进程轮转的JSONL，独立于Gunicorn日志级别；每条API请求记录账号、客户端ID、TCP来源IP、客户端系统、路由模板、状态码、响应大小、服务端耗时及SQL执行次数/耗时/错误次数。401、403、409、503也记录，不保存密码、JWT、请求体、查询参数或SQL参数。')
    add('SQLAlchemy事件计时仅包含游标执行，不含连接等待或事务提交。服务端app耗时包含鉴权和序列化；客户端latency另含网络。X-Request-ID可关联客户端CSV与服务端记录；Server-Timing同时提供app与sql。')
    checks=load('access-log-validation.json')
    table(['访问场景','客户端CSV / 服务端匹配'],[[name,f"{row['requests']} / {row['matched']}"] for name,row in checks.items()],[300,210])
    add('四组共1000条全部匹配；Linux两个Gunicorn worker均有记录。access-log-samples.jsonl保留实测原始记录，各场景server-summary.json按账号/客户端汇总。启动时日志目录不可写会失败；运行中写盘失败显式告警，已提交业务保持真实响应，不能把文件日志等同于事务审计账本。','small')
    add('部署与切换','h2')
    add('Windows/Linux统一入口为python -m tools.serve；默认127.0.0.1单机，加--host 0.0.0.0供局域网。浏览器访问服务器IP:5001，数据库3306仅供后端。多服务端连接同一权威MySQL；数据库迁移时先停写、备份、恢复校验再切换。详见“多平台部署与日志验收.md”。')

    heading(10,'实践六：订单履约界面')
    for name, caption in [('orders','订单履约：客户筛选、跨表汇总、明细、下单、发货与取消。'),('inventory','商品库存：SKU/名称查询、分仓数量、商品维护与入库。')]:
        if name == 'inventory': heading(10,'业务界面：商品与库存')
        shot=EVIDENCE/'screenshots'/f'{name}.png'
        if not shot.exists(): raise RuntimeError(f'Missing screenshot {shot}')
        from PIL import Image as PILImage
        with PILImage.open(shot) as im: w,h=im.size
        story.append(Image(str(shot),width=510,height=510*h/w));add(caption,'small')
        if name == 'orders':
            add('页面操作与数据关系','h2')
            add('客户筛选使用服务端查询；订单列表按ID倒序分页。点击编号查看商品明细与成交价，金额由明细聚合而来。新建订单选择一个客户、一个发货仓库和多条商品；服务端事务验证库存并扣减。待发货订单显示发货和取消操作，终态订单显示物流号或返库提示。')
            add('表格数据来自实际数据库，截图中的25000笔历史订单是初始化模拟数据。更新时间来自当前成功查询；查询失败显示错误而不伪装成零条记录。')
    add('保留蓝灰配色及Element Plus表格、表单、弹窗，去除宣传式标题与装饰卡片。采用紧凑查询工具栏、计数、更新时间、右对齐金额与可滚动表格。已验证空状态、金额表单、业务员权限和390px窄屏布局。')

    heading(11,'验证结果、恢复与提交')
    table(['验证项','结论与证据'],[
        ['MySQL集成测试','Linux与Windows各17/17通过，含并发、回滚、权限、持续日志及数据库故障；tests.xml / tests-windows.xml。'],
        ['前端页面回归','实际浏览器登录、数据展示与表单检查；价格框默认step=1造成1.00无效的问题已改为0.01；可执行DOM回归脚本在frontend/tests。'],
        ['备份恢复','mysqldump真实数据备份恢复至独立空库；8表CHECKSUM逐一一致，并检查订单25000行和客户1的代表值。'],
        ['源码与构建','Python编译通过；课程版Vite生产构建通过。Element Plus分包仍有体积提示，不影响运行，压缩包不含node_modules。'],
        ['旧工程基线','原后端69通过/1失败：旧数据库连接认证失败返回503；原前端构建通过但有既有警告。旧工程与本提交运行隔离。'],
    ],[120,390])
    add('恢复与重现实验','h2')
    code('mysql course_inventory < data/schema_mysql.sql\nmysql course_inventory < data/backup_mysql.sql\n# from code directory, with private environment configured:\npython -m tools.manage counts\npython -m tools.manage ddl-demo\npython -m tools.manage index-demo\npython -m pytest tests/ -v\npython -m tools.benchmark --base-url http://SERVER:5001 \\\n  --clients 8 --requests 40 --output ../doument/evidence/run')
    add('真实密码不在提交包内：恢复后用set-password设置admin/clerk密码，JWT与数据库连接通过环境变量提供。详细安装、账号、备份和故障排查见“部署与验收.md”。')
    add('提交清单','h2')
    add('将顶层目录改为本人“学号_姓名”，补全报告封面，保留data/code/doument三目录，再生成RAR并执行rar t。包内提供源代码与前端构建；不包含虚拟环境、node_modules、物理数据库、嵌入运行时或旧教务项目。最大100MB，最终大小以交付说明的实际检测为准。')
    add('实现与引用说明：业务代码为此次课程重构，样式令牌源于提供的旧项目；框架与驱动为基础依赖，未下载第三方成品业务系统。学生应按课程独立完成与辅助工具规则核对提交，并能解释模型、SQL、事务和测量方法；本报告不代签个人独立完成声明。','small')

    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#e2e8f0'));canvas.line(42,40,553,40)
        canvas.setFont(FONT,8);canvas.setFillColor(MUTED)
        canvas.drawString(42,27,'序仓 · 数据库课程作业1 | 2026-10-11')
        canvas.drawRightString(553,27,str(doc.page))
    path=DOC/'课程作业1项目报告.pdf'
    SimpleDocTemplate(str(path),pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=54,
        title='序仓：企业订单与库存管理 - 课程作业1项目报告',author='学号/姓名待填写').build(story,onFirstPage=footer,onLaterPages=footer)
    print(path)


if __name__ == '__main__': build()
