# 提交目录与清理说明

## doument/evidence 是什么
当前实际目录拼写为 `doument`（并非 document）。它存放项目报告、需求核查和部署验收文档；`evidence` 是报告结论的验证证据，包含测试 XML、压测 CSV/JSON、数据库行数与恢复验证、索引实验、日志关联验证以及界面截图。应用启动不读取它，但答辩、复现和验收会使用它。既有 evidence 是历史验证，不能代表本次改动已通过全部测试；应保留日期和测试范围，不用新文件冒充旧测试结果。

## code 内建议保留
- backend/：模型、认证、业务控制器、API 与日志实现。
- frontend/src/、index.html、package.json、package-lock.json、vite.config.js：完整前端源码和可复现构建配置。
- frontend/dist/：本项目 Flask 直接提供的生产页面；提交直接运行包应保留。应由最新源码重新 build，打包时只取最新构建结果，不手动挑选带哈希的资源。
- tools/、deploy/、tests/、frontend/tests/：初始化/生成/运行工具、部署配置和回归测试，建议保留用于复现。
- Setup/ 的脚本、依赖清单与说明：全新 Windows 安装、环境检查和后台启停入口；应随源码提交。
- requirements.txt、.env.example、README.md、API.md、.gitignore：安装配置模板和说明。
- 上级 data/ 的 SQL 建表脚本、备份及模型源文件：用于恢复数据库，不属于缓存。不要因不在 code 内而漏交。

## 可从提交压缩包排除（不必删除工作副本）
- frontend/node_modules/：第三方依赖，可用 npm ci 重装；本次运行目录约 98.89 MB，是主要体积来源。
- .venv/、venv/（若有）：本机 Python 环境，用 requirements.txt 重装。
- 所有 __pycache__/、*.pyc、.pytest_cache/：自动生成缓存。
- .idea/、.vscode/：个人编辑器配置（若包含必需共享配置，则保留该部分）。
- runtime_logs/ 的日常运行日志：可排除；已选入 evidence 的验收日志另行保留。服务运行时不要直接删除正在写入的文件。
- .git/、临时文件、旧构建/备份目录（若有）：不属于课程源代码交付。
- 真实 .env、账号口令、连接密钥：不可随包提交，使用 .env.example 和部署说明替代。
- Setup/.local/：本机配置、进程记录和专用数据库管理凭据，必须排除；`.venv-old-*` 修复备份同样排除。打包工具已包含这两类排除规则。

MODELING_UI_PROPOSAL.md 与 OPTIONAL_BACKEND_PLAN.md 是设计过程资料，可保留或挪入文档目录；体积很小，删掉几乎不能缩减包大小。

如果仅交源码，可以排除 frontend/dist，但必须说明先 npm ci && npm run build；否则当前 Flask 页面无法直接访问。推荐提交源码 + 最新 dist，排除 node_modules 与缓存。

本次仅整理说明，没有删除用户文件。
