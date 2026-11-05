# 数据库课程作业1

Windows 用户可从 `Setup/FirstRun.cmd` 完成首次安装与配置，随后使用 `Setup/Start.cmd`、`Setup/Stop.cmd`；`Setup/Manager.cmd` 提供环境检查修复、状态、重启、配置和诊断。Linux 使用 `bash Setup/linux/setup.sh` 首次配置，日常使用 `bash Setup/linux/manager.sh start --no-browser` 和 `stop`。详见 [Setup 使用说明](Setup/README.md) 与 [新手从零启动教程](Setup/新手从零启动教程.md)。安装工具只管理本课程应用，使用本机私有配置，不依赖外层教务项目。

这是课程应用。前端包含总览、订单履约、商品与库存、模型与代码，登录嵌入工作台入口。关系模型包含 8 表；默认且唯一实测运行数据库为 MySQL 8。

从上级目录 `doument/多平台部署与日志验收.md` 开始，Linux数据库初始化详见 `doument/部署与验收.md`。`data/schema_mysql.sql` 是模型自动生成的建表脚本；`data/backup_mysql.sql` 是真实 MySQL 导出的初始数据备份，两者组合可在空库完整恢复。`schema_sqlserver.sql` 同步生成供模型兼容参考，课程应用与实验命令使用 MySQL，不宣称 SQL Server 运行测试通过。

目录：

- backend/models.py：关系模型、约束、索引；建模单一来源。
- backend/controllers.py：业务事务、行锁、跨表查询。
- backend/app.py：应用工厂、蓝图、统一错误与请求耗时。
- backend/observability.py：持久化分进程访问日志、用户/客户端关联、SQL及服务端耗时。
- tools/access_report.py：按用户和客户端聚合访问性能。
- tools/serve.py：Windows/Linux通用Waitress生产入口。
- backend/security.py：共享 bcrypt 密码帮助函数、JWT 与角色授权。
- frontend/src：Vue 3、Element Plus、Pinia；沿用原项目颜色令牌。
- tools/manage.py：模型转 DDL/ERD、初始数据、计数、建表删表与索引实验。
- tools/benchmark.py：多账户多客户端 HTTP 压测及 CSV/JSON 性能记录。
- tests/test_mysql.py：真实 MySQL 集成、事务、权限和并发测试。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 按部署说明创建空库、导入 schema 与 backup、设置本机密码和 JWT_SECRET
gunicorn --workers 2 --threads 4 --bind 0.0.0.0:5001 'backend.app:create_app()'
```

已包含前端生产构建，运行无需 Node.js。开发时在 frontend 下 `npm ci`、`npm run dev`；构建用 `npm run build`。依赖未打包。Windows/Linux均可作服务端：`python -m tools.serve` 默认本机访问，加 `--host 0.0.0.0` 支持局域网；Linux也可使用Gunicorn。PDF指定Linux服务端的演示请使用Linux方案。

本项目不依赖原根目录 backend、frontend、便携 MySQL、嵌入 Python 或 config.ini。打包不包含 node_modules、虚拟环境、数据库物理文件、真实连接密码、Git 历史与软件工程扩展计划。

提交清理建议详见 `SUBMISSION_GUIDE.md`，不要直接删除业务数据库或提交真实环境密钥。
