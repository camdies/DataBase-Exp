# 订单与库存课程版 API

Flask + SQLAlchemy Core + MySQL。所有业务数据属于同一企业，admin 与 clerk 被显式授权共享订单。

响应：`{success:true,data:...,message:"操作成功"}`。错误响应带 `code`、`message`、`request_id`，HTTP 状态：401 未登录、403 无权、404 不存在、409 冲突、422 输入错误、503 数据库不可用、500 未知异常。每次响应含 `X-Request-ID` 与 `Server-Timing`；不得把错误当空列表。

使用 Setup 后台入口时，正常响应额外包含 `X-Course-Instance`（随机运行实例标识，仅供本机启动检查，不用于鉴权）。正常停机排空阶段，已进入业务处理的请求继续完成；包装层拒绝的新请求可返回 HTTP 503 纯文本提示，不经过业务 JSON/日志中间件。原 `tools.serve` 入口不添加此实例头。

除登录外，所有接口需要 `Authorization: Bearer <token>`。JWT 有效期 4 小时；每次鉴权读取当前账号角色。退出清除浏览器会话中的 token，本课程版不实现服务端即时 token 撤销。API 仅适合可信课程局域网；公网部署应增加 TLS、登录限流和会话撤销。

| 方法与路径 | 权限 | 参数 / 结果 |
|---|---|---|
| POST /api/login | 公开 | JSON username, password → token, username, role |
| GET /api/references | admin/clerk | keyword 可选，按客户姓名匹配，最多 50 个；返回 customers 与 warehouses |
| GET /api/products | admin/clerk | keyword, page（从1开始），每页20；返回 total, items，商品含 stocks 分仓数量 |
| POST /api/products | admin | sku（唯一，≤40）、name（≤80）、price（正数，2位小数）→ id；201 |
| PUT /api/products/{id} | admin | 同上，完整更新商品档案；历史订单单价保持不变 |
| DELETE /api/products/{id} | admin | 仅无库存、无订单引用的商品可删；删除相应零库存行 |
| POST /api/stock/restock | admin | product_id, warehouse_id, quantity（1–1000000）→ 新 quantity |
| GET /api/orders | admin/clerk | page, customer_id, status, keyword 可选；每页20条；返回 total, items, counts；跨表返回客户、仓库、操作员、订单总额、物流单号 |
| GET /api/search | admin/clerk | keyword 必填，1–80字符；返回 orders/products/customers 各最多5项及 order_total/product_total |
| GET /api/inventory/summary | admin/clerk | 全库 product_count、available_quantity、low_stock_count、warehouse_count |
| GET /api/overview | admin/clerk | days=7/30/90，默认30；一致性快照返回指标、趋势、状态、分仓订单与最近6单 |
| GET /api/orders/{id} | admin/clerk | 返回明细数组，含 SKU、名称、quantity、unit_price |
| POST /api/orders | admin/clerk | customer_id, warehouse_id, request_key(UUID), items:[{product_id,quantity}]；1–20行，不允许重复商品，单行1–10000；201 返回 id |
| POST /api/orders/{id}/ship | admin/clerk | tracking_no（唯一，≤60）；仅 pending → shipped |
| POST /api/orders/{id}/cancel | admin/clerk | 无请求体；仅 pending → cancelled，原子返库 |

重复 request_key 返回 409，不再扣库；它是防重复提交键，不返回上一次请求的成功结果。网络超时后应先刷新订单确认结果，再决定是否创建新订单。相同单号、SKU 或外键冲突统一 DATA_CONFLICT。数据库死锁/锁超时返回 RETRY_TRANSACTION，客户端不自动重放写操作。

金额是十进制定点字符串；时间是 UTC ISO8601（Z 后缀），浏览器转换成本地时区。查询使用绑定参数或 SQLAlchemy 表达式。普通业务数据库账号只有 SELECT/INSERT/UPDATE/DELETE 权限；建表删表实验通过管理 CLI 和单独 DDL 账号完成，无任意 SQL 执行接口。

## 客户端与观测

### 查询扩展口径

全局搜索去首尾空白后要求1–80字符，否则422。订单支持数字或 # 前缀订单号精确匹配、客户姓名及订单内商品名称/SKU包含匹配；商品与客户为字面包含匹配，百分号和下划线不当作通配符。结果保持现有业务列表排序，多条商品明细命中不会重复订单。

订单 status 仅允许 pending/shipped/cancelled 或空，非法值422。keyword 最多80字符，过长沿用列表截断规则。counts={all,pending,shipped,cancelled} 基于当前客户/关键词范围，不受所选status影响；total为状态过滤后的数量。分页仍每页20条。

库存汇总统计全库，不随搜索和分页变化。低库存按每个商品全部仓库数量合计小于10，包含0，按商品去重。当前为三仓，随实际仓库集合统计；单仓琥珀色提示仍按该仓小于10展示。所有聚合为实时读取，并发写入时多次查询之间可能存在短暂差异，刷新重新取样。

无新增业务写权限或表结构。运营总览已启用；数据库实验室仍隐藏。建模与代码栏目仅有设计方案 MODELING_UI_PROPOSAL.md，未注册路由。

总览统计：order_count 包含全部历史订单（含已取消），pending_count/status_counts 为当前状态；shipped_today 按 shipment.shipped_at 统计上海时区当日，available_quantity 为全部仓库当前可用库存合计。trend 含当天在内的近 days 个上海日历日，分别按下单/发货时间计数，无事件日期填0，不以示意图数字代替。时间列按UTC存储，查询边界转换为UTC。返回 timezone=Asia/Shanghai、generated_at、days、warehouses（包含0订单仓库）、recent_orders（金额定点字符串）及上述指标。MySQL读取使用 REPEATABLE READ 单一快照，无写锁；days非法返回422。无同比/环比、SLA、压测等未定义指标。

可选请求头 `X-Client-ID`、`X-Benchmark-ID` 限1–64个字母/数字/下划线/连字符，无效值不入日志。身份仍仅依据JWT及数据库账户。浏览器为每个会话生成客户端ID。响应 `Server-Timing` 同时给出app/sql毫秒；SQL耗时不含连接池等待、提交或回滚。

每次API请求写入 ACCESS_LOG_DIR 指定的分进程轮转JSONL，记录用户、来源IP、客户端系统、状态码、SQL次数/耗时、服务端耗时。不记录口令、令牌、请求体、查询参数。运行中日志写失败返回 `X-Access-Log-Status: failed` 并产生CRITICAL告警，已提交的业务结果不会被伪报失败。连接池耗尽返回503 DATABASE_BUSY。

账号不限于初始admin/clerk；管理员使用tools.manage create-user创建独立账号。登录密码按原始字节校验，前后空格也是密码的一部分。

## 模型与代码
GET /api/model：admin/clerk，只读返回8表结构、字段、索引、约束及模型摘要。POST /api/model/generate：admin，内存编译返回 files 和 version；文件固定为 schema_mysql.sql、schema_sqlserver.sql、model.mmd。不接受自定义SQL或路径，不执行数据库DDL。


### 模型页补齐（2026-10-29）
`GET /api/model` 的表新增 `description`，列新增 `description`；`indexes` 列出显式索引及主键、唯一约束，新增 `kind`（INDEX / UNIQUE / PRIMARY KEY）。未命名约束显示为未命名，不虚构数据库物理索引名称。中文说明来自应用内字段释义，结构来自 SQLAlchemy 元数据。

`POST /api/model/validate`：admin / clerk 可调用，必须认证，无请求参数，返回 `valid, issues, version, checks, scope`。检查主键存在、外键目标可解析、MySQL 和 SQL Server 建表/索引编译；发现问题返回 valid=false 和问题列表。不会连接数据库执行 DDL，不代表对真实数据或第三范式的证明。
