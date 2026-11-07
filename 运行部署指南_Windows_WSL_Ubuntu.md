# Windows、WSL、Ubuntu 后端运行部署指南

更新：2026-11-07。适用本目录的订单与库存课程系统。数据库使用 MySQL 8.0.16+，不是 SQL Server，也不接受 MariaDB。浏览器客户端只访问网页端口，不直接访问数据库。

## 1. 先选择服务器放在哪里

| 方案 | 服务器运行位置 | 浏览器位置 |
|---|---|---|
| Windows | Windows 上运行 Python 与 MySQL | 本机或局域网其他电脑 |
| WSL2 Ubuntu 24.04 | Windows 内的 Linux 环境 | Windows 浏览器；局域网需要额外网络配置 |
| Ubuntu 24.04 虚拟机/实体机 | 独立 Ubuntu | Ubuntu 本机或其他电脑 |

选一种作为日常运行环境即可，避免同时占用5001端口。准备完整的“学号_姓名”目录，必须包含 code、data、doument。不要只拷贝 code。首次安装需联网，下载运行时、Python包和前端依赖。预留数GB磁盘空间。前端第一次配置会重新编译，普通 start 不编译。

不要跨系统复制 .venv、Setup/.local、node_modules 或数据库物理目录。每个系统建立自己的环境与配置。业务数据迁移应使用 MySQL 逻辑备份；首次初始化使用交付的 data/schema_mysql.sql 和 backup_mysql.sql。

## 2. Windows 从零运行

1. 完整解压到有写权限的位置，例如 D:\课程作业\学号_姓名。
2. 打开 code\Setup，双击 FirstRun.cmd。缺少 Python 会安装；工具在项目私有目录自动下载 Node.js 24.16.0、核对 SHA256，然后安装前端依赖并编译。不会修改系统 Node.js 或系统 PATH。
3. 构建耗时较长时查看终端显示的日志路径。网络失败可修复网络后重试，不要删除数据库。
4. 数据库方式选3“本机专用 MySQL”。缺少 MySQL/VC++ 时可能弹出管理员授权。脚本使用独立数据目录及3307–3406中的空闲端口，不接管已有 MySQL 数据目录。
5. 输入新的数据库名、应用数据库账户密码、网页 admin 与 clerk 密码。网页密码至少10个UTF-8字节；密码输入不显示字符是正常现象。已有同名数据库不会覆盖。
6. 网页端口默认5001；只在本机访问选1，多电脑访问选2。
7. 出现启动成功后打开 http://127.0.0.1:5001 ，使用 admin 和刚设置的网页密码登录。数据库密码与网页登录密码是不同用途。

日常双击 Start.cmd / Stop.cmd。关闭窗口不代表停止服务。重新编译：Stop.cmd → BuildFrontend.cmd → Start.cmd。总菜单 Manager.cmd 的10为构建，6为状态。Stop 默认保留数据库运行；需要连同本项目专用数据库关闭，在 code PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe -m Setup.manager stop --with-database
```

Windows 局域网访问：先通过菜单配置局域网模式，再用 ipconfig 查服务器的局域网 IPv4。其他电脑访问 http://服务器IP:5001。若被防火墙阻挡，在管理员 PowerShell 中按需要建立仅限私有网络及本地子网的规则：

```powershell
New-NetFirewallRule -DisplayName 'CourseInventory 5001' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5001 -Profile Private -RemoteAddress LocalSubnet
```

不需要开放3306/3307给浏览器。不要为了排障关闭整个防火墙。

## 3. WSL 安装与配置（命令在 Windows 中执行）

需要支持虚拟化的 Windows；如提示虚拟化不可用，先检查任务管理器的CPU虚拟化状态及 BIOS/UEFI 设置。在管理员 PowerShell 执行：

```powershell
wsl --list --online
wsl --install -d Ubuntu-24.04
```

按提示重启 Windows。打开 Ubuntu 24.04，创建 Linux 用户名和密码；它与 Windows 登录密码无关，sudo 会要求这个密码。随后在 Windows PowerShell 确认：

```powershell
wsl --update
wsl --list --verbose
```

Ubuntu-24.04 的 VERSION 应为2；若为1，先备份重要数据再执行 `wsl --set-version Ubuntu-24.04 2`。已安装该发行版就无需重复安装。官方说明：[安装 WSL](https://learn.microsoft.com/en-us/windows/wsl/install)。

推荐把交付包复制到 Linux 家目录，避免共享盘权限和小文件性能问题。以下在 Ubuntu 终端执行；先确保源目录是去除了私有运行环境的交付副本：

```bash
mkdir -p ~/coursework
cp -r '/mnt/d/课程作业/学号_姓名' ~/coursework/
cd ~/coursework/学号_姓名/code
bash Setup/linux/setup.sh --no-browser
```

将 `/mnt/d/课程作业/学号_姓名` 换成实际交付包路径。不要使用 sudo 运行整个 Setup。后续选择数据库与密码的步骤与 Windows 相同。脚本仅在安装系统软件时单独调用 sudo。Linux 使用自己的 Node.js，不调用从 Windows PATH 继承的 npm。

Windows 本机浏览器通常可直接访问 http://localhost:5001。WSL 默认 NAT 模式下，其他电脑不能仅靠 Windows 防火墙放行就访问到 WSL，需要端口转发或镜像网络。最容易验收的是先确保 Windows 本机浏览器正常，再配置局域网。

### WSL NAT 模式局域网转发

先将 Setup 访问模式设为局域网，使服务监听0.0.0.0。在管理员 Windows PowerShell 执行下面查询：

```powershell
wsl -d Ubuntu-24.04 hostname -I
```

选择其中用于 WSL 网络的 IPv4；将下面的172.20.10.2替换成实际地址。示例使用Windows端口5002转发到WSL端口5001，避免与本机服务混淆：

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=5002 connectaddress=172.20.10.2 connectport=5001
New-NetFirewallRule -DisplayName 'CourseInventory WSL 5002' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5002 -Profile Private -RemoteAddress LocalSubnet
netsh interface portproxy show all
```

其他电脑访问 http://Windows局域网IP:5002。WSL重启后IP可能变化，需更新对应转发。撤销本例规则：

```powershell
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=5002
Remove-NetFirewallRule -DisplayName 'CourseInventory WSL 5002'
```

Windows11支持的镜像网络是另一条路线，还需检查Hyper-V防火墙；不要与NAT步骤混用。详见[微软WSL网络说明](https://learn.microsoft.com/en-us/windows/wsl/networking)。不要使用 wsl --shutdown 代替应用正常停机，它会停止所有WSL发行版；先执行本指南的 stop --with-database。

## 4. 独立 Ubuntu 24.04 或虚拟机配置

安装 Ubuntu 24.04，创建有sudo权限的普通用户。建议虚拟机分配至少2核、4GB内存及20GB可用磁盘作为课程实验起点，实际需求随数据量变化。需要同局域网直接访问时选择桥接网络；NAT模式则在虚拟机软件中配置宿主端口到客体5001的转发。学校网络可能限制桥接或客户端互访。

复制完整交付包到家目录。在 Ubuntu 终端：

```bash
cd ~/coursework/学号_姓名/code
bash Setup/linux/setup.sh --no-browser
```

Ubuntu24.04上会按需安装Python/venv；选择本机专用MySQL且缺少mysqld时才安装mysql-server。连接远程MySQL不强制安装本机数据库。自动Node支持Linux x64/arm64；其他发行版需自行准备Python3.12+、venv及所需MySQL，并确认Node官方二进制能运行。

日常命令（在code目录执行）：

```bash
bash Setup/linux/manager.sh check
bash Setup/linux/manager.sh start --no-browser
bash Setup/linux/manager.sh status
bash Setup/linux/manager.sh restart --no-browser
bash Setup/linux/manager.sh stop
bash Setup/linux/manager.sh build-frontend
bash Setup/linux/manager.sh start --no-browser
# 不再使用时，可关闭本项目专用数据库
bash Setup/linux/manager.sh stop --with-database
```

check 是只读检查，不会启动已停的数据库；因此数据库已停时检查失败是预期。首次配置已有.env时重新构建、验证并启动，不会重新导入数据。无图形桌面请始终使用 --no-browser。

用 `hostname -I` 查Ubuntu地址。设置局域网模式后，从其他电脑访问 http://Ubuntu地址:5001。若UFW已启用，只放行实际可信网段，例如 `sudo ufw allow from 192.168.1.0/24 to any port 5001 proto tcp`，按实际网段替换。通过SSH操作时，不要在未放行SSH的情况下贸然启用防火墙。

## 5. MySQL / SQL 配置指导

### 方式3：本机专用MySQL（新手推荐）

向导自动创建独立实例、新库、新应用账户，导入 schema_mysql.sql 和 backup_mysql.sql，并核对初始数据行数。只需填写向导中的密码，不需要手动运行SQL。专用MySQL只监听回环地址；客户端经过Python后端访问。

实例配置与root随机密码位于 Setup/.local/mysql.json（私有文件，不要分享）；Windows数据通常在 %LOCALAPPDATA%/CourseInventory，Linux在 ~/.local/share/CourseInventory。移动代码目录时需保留对应配置，不能把它当通用交付文件复制给其他人。

### 方式2：在已有MySQL上创建新库

需要有建库、导入、创建账户及授权能力的管理账号。Ubuntu系统MySQL的root常使用socket认证，`sudo mysql`能进入不等于它能通过TCP密码登录。不要盲目修改root认证方式。新手优先使用方式3；必须使用系统实例时，由数据库管理员提供临时配置账户，并在配置结束后撤销其权限。

系统MySQL的安装和状态查看示例：

```bash
sudo apt update
sudo apt install mysql-server
sudo systemctl start mysql
sudo systemctl status mysql
sudo mysql
```

在MySQL提示符中可执行以下只读检查：

```sql
SELECT VERSION();
SHOW DATABASES;
SELECT USER(), CURRENT_USER();
EXIT;
```

若WSL没有systemd，以上systemctl命令不适用；使用发行版服务管理方式，或直接使用Setup专用实例。Ubuntu官方指导：[安装与配置MySQL](https://ubuntu.com/server/docs/how-to/databases/install-mysql/)。

向导中输入MySQL主机、实际端口、管理账户及密码，选择不存在的新库名。Setup创建应用账户并限制为SELECT、INSERT、UPDATE、DELETE，应用不保存外部管理密码。不要用管理账户作为日常应用账户。

### 方式1：连接已经初始化的库

填写已具备8张业务表的数据库，以及有业务读写权限的应用账户。此方式只验证，不导入SQL、不重置网页登录密码。空库应选择方式2或3。数据库用户名不是网页登录admin用户名。

远程MySQL需要管理员配置监听地址、防火墙以及精确的后端来源授权。授权来源是Python后端机器，不是每个浏览器客户端。仅向后端IP开放数据库端口；不要用 '%' 作为默认来源。示例由管理员在目标服务器执行，替换库名、账号、实际来源IP与强随机密码：

```sql
CREATE USER 'course_app_remote'@'192.168.1.20' IDENTIFIED BY '替换为自行生成的强随机密码';
GRANT SELECT, INSERT, UPDATE, DELETE ON course_inventory.* TO 'course_app_remote'@'192.168.1.20';
SHOW GRANTS FOR 'course_app_remote'@'192.168.1.20';
```

迁移后端主机可能需要调整来源授权。部署仅面向可信课程局域网；跨不可信网络应另行配置TLS或VPN。

### 导入失败与备份

不要向已有业务库重复执行交付SQL。MySQL DDL不能整体回滚；Setup在部分失败时保留现场并记录needs-review。检查日志后修复已有库并选择方式1，或使用新库名重新初始化，不要直接删库。

备份可用 `mysqldump -h 127.0.0.1 -P 实际端口 -u 备份账户 -p --single-transaction --result-file=backup.sql 实际库名`；账户需要相应备份权限。使用-p交互输入密码，不把密码写在命令中。恢复应在单独新库中验证，不能把数据库物理目录直接从Windows复制到Linux。

## 6. 验收和常见问题

1. status显示运行；浏览器能加载登录页面。
2. admin/clerk分别登录，查询库存、订单；两浏览器并行访问。
3. stop后网页请求失败，start后恢复；重启不应重置数据或密码。
4. 停机后构建成功，再启动，check中的源码与构建记录检查通过。
5. 另一台电脑访问时，先排查服务器监听模式，再排查IP、虚拟机网络、端口转发及防火墙。

构建日志在runtime_logs/setup/frontend-*.log；快速启动不编译。下载摘要失败不要跳过验证；修复网络后重试。构建成功保留旧dist-backup-*，确认无需回退后可人工清理。构建记录过期时重新编译。若Linux私有MySQL遇到权限/AppArmor问题，查看实例mysql-error.log；不要全局关闭安全策略，可改用已管理的MySQL实例。

当前默认采用Setup管理服务。deploy/course-inventory.service是另一种Gunicorn/systemd部署模板，有独立环境文件和目录要求，不能与Setup在相同端口重复启动。Setup本次不自动配置开机自启。

### WSL无法下载Node.js时的缓存准备

如果Windows能联网而WSL无法连接nodejs.org，可在Windows从官方 https://nodejs.org/dist/v24.16.0/ 下载 `node-v24.16.0-linux-x64.tar.xz`（ARM64系统选择linux-arm64），放入Linux项目的 `code/Setup/.local/runtimes/` 后重试构建。不要解压，不要改文件名；脚本仍将校验固定SHA256。Windows zip不能代替Linux归档。npm依赖仍需网络或完整npm缓存；缓存安装包不代表所有依赖都已离线准备好。
