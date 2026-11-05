# 课程系统安装与启动工具

支持 Windows x64 与 Linux 服务端，数据库使用 MySQL。Linux 自动安装依赖面向 Ubuntu 24.04。脚本仅管理本课程版，不读取外层教务项目配置。正常运行使用已经交付的 frontend/dist，不需要 Node.js。先完整解压 `学号_姓名`，保留与 code 同级的 data 目录。零基础操作见 [新手从零启动教程](新手从零启动教程.md)。

Linux 首次运行：`bash Setup/linux/setup.sh`；日常运行：`bash Setup/linux/manager.sh start --no-browser`，将 start 替换为 check、status、restart、stop、configure、diagnostics 可使用相应功能。整个脚本以普通用户运行，仅 apt 安装步骤使用 sudo。MySQL socket/PID 文件与数据目录均隔离。

## 日常使用

| 入口 | 功能 |
|---|---|
| FirstRun.cmd | 检测或安装 Python，创建 .venv、安装依赖，进入数据库配置向导 |
| Manager.cmd | 总菜单：配置、检查修复、启动、停机、重启、状态、日志、诊断 |
| CheckRepair.cmd | 只读检查后，可选择修复项目 Python 环境；不会重建数据库 |
| Start.cmd | 后台启动、验证 HTTP 与数据库，打开浏览器；重复运行不创建第二个服务 |
| Stop.cmd | 请求正常停机，等待在途请求及响应输出完成；不停止共享数据库 |

关闭菜单或启动窗口不会关闭后台服务。退出菜单不会停机。默认网页地址为 `http://127.0.0.1:5001`；局域网模式需用服务器的真实 IP，不能访问 0.0.0.0。脚本不自动修改防火墙。

## 全新电脑配置

1. 双击 FirstRun.cmd。需要联网下载运行时和 Python 依赖；Python 安装在当前用户目录，MySQL 与 VC++ 运行库安装可能需要 UAC 管理员授权。不依赖 winget。无需安装 Git、PyCharm 或 Node.js。
2. 选择数据库方式：
   - **连接已有库**：填写应用账户，验证现有业务表。不会重设密码或导入数据。
   - **已有 MySQL 上创建新库**：临时输入具有建库、导入及创建账户权限的管理账户；只创建不存在的新库和新账户。
   - **本机专用 MySQL（默认）**：复用已安装的 mysqld 二进制；不存在时安装固定版本。为本项目创建独立数据目录和配置，选择空闲的 3307–3406 端口，仅绑定回环地址。不接管机器上其他数据库服务。
3. 创建新库时设置应用数据库密码及网页 admin/clerk 密码（网页密码10–72 UTF-8字节）。自动导入 `data/schema_mysql.sql`、`data/backup_mysql.sql`，逐表核对106005行初始数据，重设网页密码，创建只有 SELECT/INSERT/UPDATE/DELETE 权限的应用账户。账户来源限制为初始化连接实际来源，不使用通配来源。远程数据库后续更换后端机器时需要调整账户来源授权。
4. 选择网页端口和本机/局域网模式。生成随机 JWT 密钥并保存私有配置，完成真实连接和页面检查后启动。

已有有效 .env 时 FirstRun 只验证，不重复导入或重设密码；通过菜单“修改配置”调整连接与端口。无效配置可在明确选择后备份到私有目录并重建。正常重启不会轮换密钥。

## 命令行

在 code 目录使用项目 Python（无需 activate）：

```powershell
.\.venv\Scripts\python.exe -m Setup.manager check
.\.venv\Scripts\python.exe -m Setup.manager start --no-browser
.\.venv\Scripts\python.exe -m Setup.manager status
.\.venv\Scripts\python.exe -m Setup.manager restart --no-browser
.\.venv\Scripts\python.exe -m Setup.manager stop
.\.venv\Scripts\python.exe -m Setup.manager stop --with-database
.\.venv\Scripts\python.exe -m Setup.manager stop --force
.\.venv\Scripts\python.exe -m Setup.manager configure
.\.venv\Scripts\python.exe -m Setup.manager diagnostics
```

`--with-database` 只关闭 Setup 创建且通过进程身份核验的专用 MySQL；不关闭外部或共享数据库。`--force` 只在正常停机超过35秒后强制停止核验过的 Web 进程，可能中断未完成请求。正常停机不提供远程控制接口。

脚本自动根据自身路径定位项目，支持中文和空格，不要求终端工作目录固定。批处理默认结束时暂停以便阅读；自动化调用前设置 `COURSE_SETUP_NO_PAUSE=1`。检查失败、安装失败及启停失败返回非零退出码。

## 文件与凭据

- `code/.env`：数据库连接、JWT_SECRET、BCRYPT_ROUNDS、ACCESS_LOG_DIR。由 Setup 按 JSON 字符串写入，兼容简单未引用值和单引号值。Setup 作为数据解析，不执行其中任何命令，也不扩展环境变量。不要将 Setup 生成的文件当 shell 脚本执行。原应用入口仍不自动加载 .env。
- `Setup/.local/`：端口设置、安装阶段、进程身份记录、专用数据库管理凭据、配置备份。Windows 使用当前用户/SYSTEM ACL，POSIX 使用仅所有者权限。不要手工分享此目录。
- `code/.venv/`：项目依赖；损坏环境会重命名为 `.venv-old-时间戳` 后重建，不自动删除。
- `code/runtime_logs/setup/`：服务输出及可分享的诊断报告；诊断仅导出白名单字段，不复制原始日志、配置、口令和 JWT。`logs` 命令列出最近日志位置，可用文本编辑器查看。
- `%LOCALAPPDATA%/CourseInventory/`：安装包缓存、专用 MySQL 实例。独立于交付包。移动 code 目录后应重建虚拟环境；保留 .local 才能继续定位原实例。不要删除此目录中的数据库文件。

新库管理凭据只在初始化过程中临时使用；外部数据库管理密码不保存。本机专用数据库的随机 root 密码存于私有 mysql.json，供启动及正常关闭使用；应用仍使用最小权限账户。

## 修复与中断恢复

- 缺 Python / .venv / 依赖：运行 CheckRepair 或 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File Setup/bootstrap.ps1 -Action repair`。仅对本次 PowerShell 进程使用执行策略参数，不修改机器策略；组织策略禁止时仍可能拒绝执行。
- 数据库连不上：检查主机、端口、账户权限和服务状态。`check` 不自动启动数据库；`start` 会启动已配置的专用实例。外部数据库服务由其管理员管理。
- 端口冲突：菜单修改端口。工具不结束占用端口的其他程序。
- SQL 导入中断：install-state.json 标记 `needs-review`，部分数据库保留。MySQL DDL 不能整体回滚。检查并修复该库后选择“连接已有库”，或使用新的库名重新初始化。工具没有删库、强制覆盖或重复灌数选项。
- 专用 MySQL 首次初始化中断：mysql.json 保留 `initializing` 状态和实例位置，后续拒绝自动重试。检查实例 initialize.log / mysql-error.log；如启动后尚未完成 root 改密，先停掉记录中的专用进程。需要重建时保留该实例目录与 mysql.json 的私有备份，然后移走这份 mysql.json，重新执行首次配置创建独立的新实例；不复用部分初始化的数据目录。
- 前端文件缺失：恢复交付产物，或自行安装合适 Node.js 后在 frontend 执行 `npm.cmd ci`、`npm.cmd run build`。正常启动不会联网安装前端依赖。
- 正常停机超时：等待在途请求完成，再检查状态；确需强制停机时显式使用 `stop --force`。

## 运行时来源与范围

安装器固定在 manifests/dependencies.json：Python 3.13.9、MySQL 8.4.6、VC++ 14.44.35211.0。下载后必须同时通过 SHA256 与 Authenticode 发布者验证才执行；不会绕过摘要校验。MySQL/VC++ 摘要来自 Microsoft winget-pkgs 对应版本清单；Python 摘要通过 Python.org 原始下载且验证 PSF 签名后记录。它们是固定复现版本，不宣称为最新版本；更新时需重新核验来源、摘要和启动兼容性。

安装缓存默认位于提交目录外。离线机器需预先准备清单对应安装器和完整 Python wheel 包；不承诺纯源码离线安装。Windows 安装器/UAC 流程仍需在干净系统验收。Linux 安装与启停入口已提供，Ubuntu 24.04 可自动安装系统依赖；备份恢复、开机启动与防火墙助手属于后续扩展。长期服务可继续使用 deploy/course-inventory.service，勿与 Setup 重复启动同一端口。

## 验证

```powershell
python -m pytest tests/test_setup.py -v
# 完整测试必须使用独立、可建库及创建临时账户的 MySQL 测试连接
# TEST_DATABASE_URL 指向 *_test 数据库，禁止使用业务库
python -m pytest tests/ -v
```

tests/test_setup_mysql.py 创建随机命名的临时数据库和账户，验证真实备份导入、密码、权限、重复导入拒绝与部分失败保留，完成后只清理自身创建的对象。测试不能作为首次配置中的“修复”操作。
