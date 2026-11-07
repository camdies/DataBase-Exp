# Setup 验证记录

## 2026-11-07 前端构建与部署流程

- 最终全量测试：Windows 54通过、1项POSIX测试跳过；Ubuntu24.04 / WSL2 55通过。真实MySQL测试使用已有隔离测试实例与独立测试库，未操作业务库。
- 两端通过真实入口执行 build-frontend、check、start、重复start、status、restart、diagnostics、stop、stop --with-database、已有配置first-run --no-browser及最终停机。首次配置重新编译后实际启动成功，不重复灌数。
- Windows自动下载并校验Node.js24.16.0；Linux直接下载遇到URLError，npm直接联网遇到ECONNRESET，随后通过Windows准备官方Linux归档及匹配锁文件的npm缓存，在Linux执行摘要校验、npm离线安装和实际生产构建成功。没有关闭TLS或绕过完整性校验。不能据此宣称当前WSL直接联网安装通过。
- 回归覆盖构建失败保留旧产物、替换失败回滚、源码变化检测、运行中拒绝构建、资源缺失、下载摘要错误拒绝执行、构建失败不进入数据库初始化、已有配置启动与no-browser参数，以及Python修复后使用新解释器继续构建。
- PowerShell解析、Linux shell语法、Python编译、文档本地链接与git diff --check通过。前端仍有大于500kB的Element Plus资源块警告，构建成功。
- 测试完成后已关闭测试Web服务及专用数据库。保留私有测试配置与缓存供复核，不应随交付包分享。
- 尚未执行：干净Windows上的UAC/运行时安装、从零安装WSL、Ubuntu系统apt安装、独立Ubuntu虚拟机与真实局域网双机验收、Linux ARM64实机测试。Linux自动系统安装仍限定Ubuntu24.04；Node归档支持不代表所有Linux发行版均完成验收。
- Windows全流程验证后补充的检查修复分支及下载错误提示，由最终全量测试覆盖；Linux最终全流程使用最终代码。项目主目录未覆盖已有frontend/dist，构建均在测试副本进行。

证据：[Windows最终测试](../../doument/evidence/setup-20261107/windows/tests.txt)、[Windows流程](../../doument/evidence/setup-20261107/windows/result.json)、[Linux最终测试](../../doument/evidence/setup-20261107/linux/tests.txt)、[Linux流程](../../doument/evidence/setup-20261107/linux/result.json)。完整本机过程记录在 D:/DataBase-Exp/tmp/setup-build-20261107，Windows最终补测在同级 setup-build-20261107-final-tests。

以下保留历史记录，各日期的范围与限制分别适用。


## 2026-11-05 跨平台补充

- 新增 Linux setup.sh / manager.sh，自动系统依赖安装限定 Ubuntu 24.04，其他 Linux 在预装依赖后复用管理逻辑。
- 实际测试环境：Windows 11；Ubuntu 24.04（WSL2，Python 3.12）。两端均使用各自的独立 MySQL 实例及虚拟环境，没有使用现有业务数据库。
- Linux 最终完整课程测试47项通过；Windows 46项通过、1项 POSIX TIME_WAIT 测试按平台跳过。两端结果文件见下方证据目录。
- 两端均验证启动、重复启动、状态、重启、停止、重复停止、停止专用数据库后再次首次配置。Linux 实测发现并修复了 mysqld 切换工作目录导致身份误判、TIME_WAIT 导致重启端口误报，以及已退出但未回收的非子进程导致停机超时误报；已有配置时启动专用数据库再验证也有新增回归测试。
- 两端分别测试1、8、16客户端，每客户端20个只读查询。每端总计500请求，全部成功；8/16客户端使用 admin、clerk 两个账号的独立登录会话。服务端按用户和客户端的统计条数与本批请求数一致。
- Windows 吞吐量分别17.21、85.96、111.21请求/秒；P95分别106.22、180.91、204.35毫秒。Linux 吞吐量29.29、113.69、123.70请求/秒；P95分别55.46、91.51、168.74毫秒。仅为本机短时负载结果，不能作为操作系统性能排名或容量承诺。
- 原始请求CSV、客户端summary.json与服务端server-summary.json位于 `doument/evidence/setup-20261105-windows` 和 `setup-20261105-linux`。
- Linux 直接访问 PyPI 超时，改用联网 Windows 下载的匹配 Linux wheel 包安装并运行测试，未关闭TLS验证。Ubuntu apt全新安装、Windows安装器/UAC、两台物理电脑的真实局域网访问仍未在本次执行；WSL2本机测试不能冒充独立物理机测试。

下面保留2026-10-30首版记录，范围与限制以各自日期为准。

日期：2026-10-30（Asia/Shanghai）。本记录仅描述本次执行，未修改历史 doument/evidence 记录。

## 已通过

- Python 编译检查及 Windows PowerShell 5 脚本解析。
- Setup 单元测试16项：特殊字符密码、配置不执行命令、弱密钥/重复键拒绝、只读检查、前端缺失、进程身份与PID复用、拒绝误停其他进程、端口冲突、诊断脱敏、互斥锁、停机时在途请求完整返回、异常迭代器释放计数、退出码、共享系统包的虚拟环境重建。
- 课程版完整 `tests/`：44项通过。使用独立临时 MySQL 实例、专用测试库；数据库真实恢复、权限、账户密码、重复初始化拒绝和部分导入失败保留均有测试。
- 在中文、空格路径的临时交付副本中验证：启动、重复启动、状态、重启、诊断报告、停止、重复停止。
- 实际 Windows bootstrap 入口验证：环境修复、已有配置的 FirstRun、启动、重启、状态和停机。
- 创建真正隔离的 .venv，按项目清单联网安装依赖，`pip check` 通过。在这套新依赖上运行上述44项完整测试。
- 前端生产构建通过，产物写入临时目录；未覆盖交付的 frontend/dist。构建保留已有的单块超过500kB提示。
- 未配置时 Start.cmd 返回1；未运行时 Stop.cmd 返回0。
- 从 Python.org 下载固定版 Python 安装器，SHA256 与 PSF Authenticode 签名校验通过；未执行安装。

主要验证环境：Windows、Python 3.13.9；隔离环境安装得到 Flask 3.1.3、SQLAlchemy 2.1.6、PyMySQL 1.2.3、Waitress 3.0.2、psutil 7.2.2。服务与数据库验证均在临时实例上完成，没有读取或修改业务数据库。

## 验证边界

- 未在全新 Windows 虚拟机中执行 Python/MySQL/VC++ 安装及 UAC/重启流程，避免在现有机器安装或替换系统软件。自动安装代码、固定来源、摘要和发布者检查已实现，但全新系统验收仍需独立机器。
- Linux 自动安装、开机启动、自动备份恢复与局域网防火墙助手不属于首版；继续使用既有部署文档。
- 联网依赖清单保留项目既有版本范围，因此今后解析到的依赖版本可能不同；本记录不代表未来版本都已测试。
- 测试服务与专用 MySQL 均已正常停止。自动安全检查阻止临时目录清理，因此 `%TEMP%/course-setup-validation-92qdcpdw` 和 `%TEMP%/course-setup-validation-3ky41emq` 保留为本机测试产物，含私有测试配置，不应随作业包提交。
