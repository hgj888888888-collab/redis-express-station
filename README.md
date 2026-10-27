# 基于 Redis 的校园快递驿站管理系统

《非结构化数据库入门》课程设计。后端用 Redis 的多种数据结构建模校园快递驿站的业务，
前端为微信原生小程序（用户端 + 管理端两个项目），全程无需虚拟机与数据库服务器。

## 技术栈

| 层次 | 技术 |
|---|---|
| 数据层 | Redis 7.4.1（Windows 绿色版），String / Hash / List / Set / ZSet / Stream / HyperLogLog |
| 后端 | Python 3.10+、Flask 3、redis-py |
| 前端 | 微信原生小程序（游客 AppID 即可运行） |

## 目录结构

```
ks/
├── express_station/          # Flask 后端
│   ├── app.py                # 路由与鉴权守卫
│   ├── db.py                 # Redis 连接与全部 Key 命名
│   ├── parcel.py             # 包裹入库、状态流转、超期闭环
│   ├── pickup.py             # 取件码生成/校验、取件、货架灯
│   ├── advanced.py           # 排队叫号、黑名单、超期提醒
│   ├── stats.py              # 状态统计、每日统计、看板
│   ├── notify.py             # 站内到件通知
│   ├── auth.py               # 管理员登录与令牌
│   ├── serializers.py        # Hash -> dict 序列化
│   ├── settings.py           # 配置常量
│   ├── seed_demo.py          # 演示数据脚本
│   └── test_api.py           # 接口自测脚本
├── miniprogram/              # 用户端小程序
├── miniprogram_admin/        # 管理端小程序（与用户端同代码，独立窗口便于双端演示）
├── _redis/                   # Redis 绿色版（**.gitignore 已排除，需自行下载**）
├── 启动系统.bat              # 一键启动 Redis + Flask
└── 打开Redis命令行.bat       # 打开 redis-cli
```

## 环境准备

1. **Python 3.10+**，安装依赖：

   ```
   cd express_station
   pip install -r requirements.txt
   ```

2. **Redis 7.4.1（Windows 绿色版）**：从 <https://github.com/redis-windows/redis-windows/releases>
   下载 `Redis-7.4.1-Windows-x64-msys2`，解压到本仓库根目录的 `_redis/` 下，最终路径为：

   ```
   ks/_redis/Redis-7.4.1-Windows-x64-msys2/redis-server.exe
   ```

3. **微信开发者工具**（导入小程序时使用）。

## 启动步骤

### 1. 启动 Redis 与后端

双击根目录的 `启动系统.bat`，脚本会自动：
- 在 6379 端口启动 `redis-server`
- 在 `express_station` 目录启动 `python app.py`（监听 `0.0.0.0:5000`）

也可手动分两步启动：

```
cd _redis\Redis-7.4.1-Windows-x64-msys2
redis-server.exe redis.conf

cd express_station
python app.py
```

验证后端是否正常：

```
curl http://127.0.0.1:5000/api/health
```

### 2. 导入小程序

1. 微信开发者工具 → 导入项目 → 选择 `miniprogram` 目录（AppID 选“测试号/游客模式”）
2. 右上角「详情 → 本地设置」勾选 **不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书**
3. 需要双端演示时，再导入一次 `miniprogram_admin` 目录，两个窗口独立运行

### 3. 修改后端地址（仅局域网/真机预览时需要）

小程序请求地址在 `miniprogram/utils/api.js` 与 `miniprogram_admin/utils/api.js` 的 `BASE_URL`：

```js
const BASE_URL = "http://172.17.176.42:5000";  // 当前为本机局域网 IP，模拟器/真机都用它
// 只想在模拟器里跑：改成 "http://127.0.0.1:5000"
```

真机预览需手机与电脑在同一 Wi-Fi，且 Windows 防火墙放行 5000 端口。

### 4. 可选：灌入演示数据

```
cd express_station
python seed_demo.py
```

## 配置项

`express_station/settings.py`，均可用环境变量覆盖：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `127.0.0.1` / `6379` / `0` | Redis 连接 |
| `REDIS_PASSWORD` | 空 | Redis 密码（可选） |
| `ADMIN_USER` / `ADMIN_PASSWORD` | `admin` / `123456` | 管理端账号（课程演示用） |
| `ADMIN_TOKEN_TTL` | `12 小时` | 管理员令牌有效期 |
| `LIGHT_TTL` | `120 秒` | 货架灯亮灯时长，到期自动熄灭 |
| `CODE_TTL` | `7 天` | 取件码默认有效期 |
| `CODE_MAX_FAILS` / `FAIL_WINDOW` | `5 次` / `600 秒` | 取件码连续错误上限与锁定时长 |

## Redis 数据模型

| Key | 类型 | 用途 |
|---|---|---|
| `parcel:id` | String | 包裹编号自增序列 |
| `parcel:{id}` | Hash | 包裹详情（收件人、单号、货架、状态等） |
| `parcel:tracking:{no}` | String | 快递单号 → 包裹 ID，作单号唯一约束（`SET NX`） |
| `user:{uid}:parcels` | Set | 某用户的包裹集合 |
| `user:{uid}:pickups` | List | 取件历史（最新在前） |
| `parcels:status:{status}` | Set | 按状态索引，统计与列表 |
| `parcels:stay` | ZSet | score=入库时间戳，滞留时长排名 |
| `parcels:expire` | ZSet | score=保管到期时间，`ZRANGEBYSCORE` 批量扫超期 |
| `rank:user:parcels` | ZSet | 用户包裹数量排行 |
| `pickup:code:{code}` | String + TTL | 取件码 → 包裹 ID |
| `parcel:{id}:code` | String + TTL | 包裹 ID → 取件码 |
| `pickup:used:{code}` | String + TTL | 已核销取件码，用于重复取件提示 |
| `pickup:fail:{ip}` | String + TTL | 取件码连续错误计数（防爆破） |
| `pickup:stream` | Stream | 取件事件日志 |
| `parcel:events` | Stream | 拒收 / 退货事件日志 |
| `stats:status` | Hash | 各状态包裹计数 |
| `stats:daily:{date}` | Hash | 每日入库 / 取件统计 |
| `stats:pickup_users` | HyperLogLog | 去重取件人数（`PFADD`） |
| `station:queue` | List | 取件高峰排队队列 |
| `station:queue:serving` | String | 当前叫号 |
| `station:queue:serving:shelf` | String + TTL | 叫号对应的亮灯货架 |
| `light:shelf:{shelf}` | String + TTL | 货架指示灯 |
| `overdue:alerts` | ZSet | 超期提醒集合 |
| `notify:{uid}` / `notify:{uid}:unread` | List / String | 站内到件通知与未读数 |
| `blacklist:users` | Set | 黑名单 |
| `admin:token:{token}` | String + TTL | 管理端令牌（一次登录一个 Key，支持多端同时在线） |

## 主要接口

| 分组 | 接口 |
|---|---|
| 基础 | `GET /api/health`、`POST /api/auth/login`（管理端登录） |
| 包裹 | `POST /api/parcels`、`GET /api/parcels`、`GET /api/parcels/{id}`、`GET /api/parcels/tracking/{no}`、`DELETE /api/parcels/{id}` |
| 状态 | `POST /api/parcels/{id}/status`、`/abnormal`、`/refuse`、`/return`、`/restore`（撤销拒收）、`/origin`（拒收件发回发出地） |
| 超期 | `POST /api/parcels/expired/sweep`（扫描）、`POST /api/parcels/expired/return`（批量退回） |
| 取件 | `POST /api/parcels/{id}/code`、`GET /api/parcels/{id}/code`、`POST /api/parcels/{id}/light`、`POST /api/pickup/verify`、`POST /api/pickup` |
| 用户 | `GET /api/users/{uid}/parcels`、`/pickups`、`/notifications`、`POST /api/users/{uid}/notifications/read` |
| 统计 | `GET /api/stats/status`、`/daily`、`/overview`、`/dashboard`、`/rank/users`、`/rank/stay`、`/pickup-users`、`/overdue` |
| 排队 | `GET /api/queue`、`POST /api/queue`（取号）、`DELETE /api/queue`（放弃）、`POST /api/queue/call`（叫下一位） |
| 运营 | `GET /api/events`、`GET/POST/DELETE /api/blacklist`、`POST /api/remind/overdue` |

鉴权说明：
- 管理端写操作与统计接口需请求头 `X-Admin-Token`（`POST /api/auth/login` 返回）
- 取件码校验与取件按来源 IP 做了 5 次 / 10 分钟的防爆破限制
- 用户维度查询（包裹、历史、通知）按学号开放，便于课堂演示

## 主要功能

- 入库自动生成取件码、分配货架，单号重复入库拦截
- 凭取件码自助取件 / 驿站代取，取件事件写入 Stream
- 货架指示灯（String + TTL 120 秒）与排队叫号联动
- 高峰排队取号、叫下一位、放弃排队
- 超期未取闭环：ZSet 到期扫描 → 标记超期 → 批量退回快递公司
- 拒收 / 退货管理：撤销拒收、拒收件发回发出地、记录原因
- 站内到件通知与未读数、黑名单
- 数据看板：状态分布、每日统计、用户排行、滞留排名、去重取件人数
- 管理端自定义 tabBar 按角色过滤，用户端/管理端双窗口演示

## 自测

```
cd express_station
python test_api.py
```

需要离线运行时，可设置 `REDIS_FAKE=1` 使用 fakeredis（仅自测，不写入真实 Redis）。

## 已知限制

- 首次使用学号无需口令即可查看包裹，因为课程演示以“学号”作为身份标识，未接入学校统一认证
- 未开启 AOF/RDB 持久化与 HTTPS，仅适合本地演示
- 微信订阅消息需要正式 AppID，当前用站内通知替代
