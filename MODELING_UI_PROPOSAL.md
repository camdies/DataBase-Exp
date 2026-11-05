# 模型与代码功能说明

更新：2026-10-29。保留原文件名方便旧链接访问；本文件描述已实现行为，不再作为待确认实施提案。

## 模型来源与页面

关系模型唯一结构来源为backend/models.py中的SQLAlchemy MetaData；backend/model_export.py将它转换为JSON、DDL和Mermaid文本。frontend/src/views/ModelView.vue通过/#/model展示8张表。App.vue将其放在“数据工程”导航分组。

已实现：表列表与图内实体选择、固定业务布局、画布拖动平移、缩放和适应画布、字段名称/类型/中文解释/非空/PK/FK/UK、外键目标、显式索引、主键与唯一约束、CHECK表达式。中文解释来自应用内字典，不是数据库注释或实时探测结果。未命名约束不伪造物理索引名。

## 权限与生成

| 操作 | admin | clerk |
|---|---|---|
| 查看模型 GET /api/model | 允许 | 允许 |
| 校验 POST /api/model/validate | 允许 | 允许 |
| 生成 POST /api/model/generate | 允许 | 403 |

接口统一使用现有JWT认证和响应封装。校验和生成没有业务参数，不接受任意SQL、路径或连接串。生成固定返回schema_mysql.sql、schema_sqlserver.sql、model.mmd三个文本文件以及version；所有方言一次生成，前端标签切换不向服务端提交方言参数。管理员可预览、复制、下载当前单个文件。生成失败清空旧结果并禁用下载；刷新模型也清空生成和校验状态。

生成内容保存在内存中，不执行DDL、不写入服务器data目录、不修改Python模型。网页请求鉴权仍会访问账号表，所以“内存生成”不等于整个HTTP请求无需数据库。生成时间是当前浏览器时间；version是结构及说明序列化后的SHA256前16位摘要，不是发布版本或数据库迁移号。

剪贴板受浏览器权限和安全上下文限制，局域网HTTP下可能不能复制；可用单文件下载或手动选择文本。

## 校验的实际范围

validate检查每表存在主键、外键目标能够解析、MySQL及SQL Server建表与显式索引能够编译。返回valid、issues、version、checks、scope；逻辑不通过时HTTP仍可为200、valid=false，应读取结果而非只看状态码。

它不验证线上数据库结构与模型一致，不扫描业务数据，也不自动证明第三范式。SQL Server仅生成DDL，没有实机运行验证。

## CLI与网页输出的区别

python -m tools.manage generate会覆盖data中的三份生成文件；网页生成只返回文本。两条路径均源于同一表结构，但不是字节一致的输出：SQL注释不同，Mermaid关系标注也不同。

CLI的data/model.mmd显式表达业务规则：订单至少一条明细（1..N）。网页根据外键与唯一性推导结构约束，普通父子关系允许零条（0..N），物流为0..1；数据库外键本身不能强制父表至少有一个子记录。图上“1:N”允许零条，订单最少一条仍由下单事务保证。不能将这两类基数混为一谈。

## 当前未实现

模型编辑、新增字段、保存图内实体位置、JSON草稿、ZIP下载、生成历史、数据库迁移执行、ORM/CRUD代码生成均未实现。当前提供代码化建模、只读可视化展示及数据库DDL/ERD导出，不宣称使用过Workbench或PowerDesigner。老师未指定专用工具，验收应展示真实工作流。

## 验证

后端test_read_queries.py包含模型接口权限、字段、索引种类、基数输出、校验失败分支；2026-10-29本次9项SQLite隔离测试通过。frontend/tests/model-ui.cjs是浏览器测试脚本，使用真实Python元数据但拦截HTTP响应；它不是生产MySQL端到端验证。本次未重跑浏览器测试。
