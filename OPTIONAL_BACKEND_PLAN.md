# 总览现状与数据库实验室保留方案

更新：2026-10-29。已实施功能与未来方案分别列出，未实施内容不作为验收结果。

## 已实施

/overview路由实际使用OverviewView.vue，不使用OverviewOptional.vue。GET /api/overview要求admin或clerk，days只允许7、30、90。数据库以UTC存储时间，以Asia/Shanghai计算日期窗口；窗口含当天，无事件日期填0。MySQL使用REPEATABLE READ单一只读快照，不加写锁。

| 字段 | 含义 |
|---|---|
| order_count | 全部历史订单，含已取消 |
| pending_count / status_counts | 当前订单状态数量 |
| shipped_today | 上海当日发货记录数 |
| available_quantity | 全部分仓stock.quantity合计，不再扣减待发货订单 |
| trend | 每日下单与发货数量 |
| warehouses | 仓库id、name、order_count，含零订单仓；占比由前端计算 |
| recent_orders | 最近6笔订单，明细先聚合后关联，金额为定点字符串 |
| generated_at / timezone / days | 生成时间、业务时区及窗口长度 |

总览没有环比、同比、24小时SLA、每日取消量和导出报表。全局搜索、状态筛选及库存汇总也已接入，精确口径见API.md。模型已由独立/model路由和/api/model接口承载，不再规划到/api/lab/model。

## 仅保留的组件

OverviewOptional.vue是早期占位组件，DatabaseLabOptional.vue是数据库实验室占位组件；均未注册路由。后者不执行事务、索引或压测任务，不显示可视为实测结果的示意数据。当前实验使用tools/manage.py、benchmark.py、access_report.py、network_demo.sh及tests/test_mysql.py。

## 实验室未来方案 尚未实施

若以后实施网页实验室，需独立实验库和专用账号，禁止接收任意SQL、文件路径、shell命令或连接串。压测应由受限任务队列异步执行，记录queued/running/succeeded/failed/cancelled状态，控制客户端数、时长和同时运行任务数，支持取消与失败结果保留。

曾讨论的/api/lab/capabilities、/api/lab/runs及其任务状态、取消、报告接口当前均不存在。不要按这些地址进行部署验收。实验室是否启用、隔离库权限和资源上限需在未来实施任务中确认；已有总览与模型权限不属于待确认事项。

实际回滚需验证数据库前后状态；索引需相同数据及参数下的EXPLAIN与采样；性能需记录环境、负载、失败数、起止时间及样本量。当前服务对死锁/锁超时返回冲突，不自动重试写操作，不能把“自动重试成功”写成现有能力。
