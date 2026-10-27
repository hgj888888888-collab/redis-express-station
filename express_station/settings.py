"""全局配置：Redis 连接参数与业务常量。"""
import os

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

# 取件码默认有效期：7 天（秒）。入库时会按包裹自身的保管期传入
CODE_TTL = 7 * 24 * 3600

# 货架指示灯亮灯时长（秒）：到期 Redis 自动删除标记，灯自动熄灭
LIGHT_TTL = 120

# 管理员账户（课程设计演示用，可通过环境变量覆盖）
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123456")

# 管理端令牌有效期（秒）：到期后需重新登录管理员账号
ADMIN_TOKEN_TTL = 12 * 3600

# 取件码防爆破：窗口内连续错误达到上限即锁定
CODE_MAX_FAILS = 5
FAIL_WINDOW = 600

# 包裹状态
STATUS_PENDING = "PENDING"    # 待取件
STATUS_PICKED = "PICKED"      # 已取件
STATUS_ABNORMAL = "ABNORMAL"  # 异常件
STATUS_EXPIRED = "EXPIRED"    # 超期未取
STATUS_REFUSED = "REFUSED"    # 已拒收（收件人不要了，退回快递公司）
STATUS_RETURNED = "RETURNED"  # 已退货（取件后申请退回）

STATUS_TEXT = {
    STATUS_PENDING: "待取件",
    STATUS_PICKED: "已取件",
    STATUS_ABNORMAL: "异常件",
    STATUS_EXPIRED: "超期未取",
    STATUS_REFUSED: "已拒收",
    STATUS_RETURNED: "已退货",
}

# 各快递公司单号前缀
COURIER_PREFIX = {
    "顺丰": "SF",
    "中通": "ZT",
    "圆通": "YT",
    "韵达": "YD",
    "京东": "JD",
    "邮政": "YZ",
}
