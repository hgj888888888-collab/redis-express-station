"""Redis 连接管理与 Key 命名规则。

设计原则：不同业务对象按数据特点选择合适的数据类型，
全部 Key 采用 "对象:标识" 的冒号分层命名，便于在 redis-cli 中按前缀检索。
"""
import os

import redis

from settings import REDIS_HOST, REDIS_PASSWORD, REDIS_DB, REDIS_PORT


class BizError(Exception):
    """业务异常：由 Flask 统一转换成 400 响应。"""


_client = None


def get_redis():
    """获取 Redis 连接（进程内单例）。

    设置 REDIS_FAKE=1 时使用 fakeredis 内存实例，仅用于离线自测；
    正常演示与截图请连接真实 Redis。
    """
    global _client
    if _client is not None:
        return _client

    if os.getenv("REDIS_FAKE") == "1":
        import fakeredis
        _client = fakeredis.FakeRedis(decode_responses=True)
        return _client

    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=3,
        health_check_interval=30,
    )
    try:
        client.ping()
    except redis.exceptions.RedisError as exc:
        raise BizError(
            "无法连接 Redis（%s:%s），请先启动 redis-server 后重试。原始错误：%s"
            % (REDIS_HOST, REDIS_PORT, exc)
        ) from exc
    _client = client
    return _client


# ---------------- Key 命名 ----------------
K_PARCEL_SEQ = "parcel:id"                       # String：包裹自增序号
K_PARCEL = "parcel:{}"                           # Hash：包裹详情
K_USER_PARCELS = "user:{}:parcels"               # Set：用户包裹集合
K_STATUS = "parcels:status:{}"                   # Set：按状态索引
K_STAY = "parcels:stay"                          # ZSet：score=入库时间戳，用于滞留排名
K_RANK_USER = "rank:user:parcels"                # ZSet：用户包裹数量排行
K_CODE = "pickup:code:{}"                        # String+TTL：取件码 -> 包裹ID
K_CODE_USED = "pickup:used:{}"                   # String+TTL：已核销取件码（短期保留，用于重复取件提示）
K_PARCEL_CODE = "parcel:{}:code"                 # String+TTL：包裹ID -> 取件码
K_USER_HISTORY = "user:{}:pickups"               # List：用户取件历史（最新在前）
K_PICK_STREAM = "pickup:stream"                  # Stream：取件事件日志
K_STATS_STATUS = "stats:status"                  # Hash：各状态包裹计数
K_STATS_DAILY = "stats:daily:{}"                 # Hash：每日入库/取件统计
K_PICK_USERS = "stats:pickup_users"              # HyperLogLog：去重取件用户数
K_BLACKLIST = "blacklist:users"                  # Set：黑名单
K_QUEUE = "station:queue"                        # List：取件高峰排队队列
K_SERVING = "station:queue:serving"              # String：当前叫号
K_OVERDUE_ALERT = "overdue:alerts"               # ZSet：超期未取提醒（score=入库时间戳）
K_LIGHT_SHELF = "light:shelf:{}"                 # String+TTL：货架指示灯（货架号 -> 包裹ID）
K_SERVING_SHELF = "station:queue:serving:shelf"  # String+TTL：当前叫号对应的亮灯货架
K_PARCEL_EVENTS = "parcel:events"                # Stream：拒收 / 退货事件日志
K_NOTIFY = "notify:{}"                           # List：用户站内到件通知（最新在前）
K_NOTIFY_UNREAD = "notify:{}:unread"             # String：未读通知计数
K_TRACKING = "parcel:tracking:{}"                # String：快递单号 -> 包裹ID（单号唯一约束）
K_EXPIRE = "parcels:expire"                      # ZSet：score=保管到期时间，批量扫描超期件
K_ADMIN_TOKEN = "admin:token:{}"                 # String+TTL：管理端访问令牌（一次登录一个 Key，支持多端）
K_PICK_FAIL = "pickup:fail:{}"                   # String+TTL：取件码连续错误次数（按来源 IP）
