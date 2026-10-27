"""管理端身份认证与访问令牌。

  String admin:token:{token}  —— 管理员登录成功后签发的随机令牌，TTL 到期自动失效。

令牌只保存在 Redis 中，服务端每次请求用 EXISTS 校验，天然支持「踢下线」，
且每次登录写入独立 Key，多个管理端窗口（或多台设备）可同时在线。
"""
import secrets

from db import BizError, K_ADMIN_TOKEN, get_redis
from settings import ADMIN_PASSWORD, ADMIN_TOKEN_TTL, ADMIN_USER


def admin_login(username: str, password: str) -> dict:
    if username != ADMIN_USER or password != ADMIN_PASSWORD:
        raise BizError("账号或密码错误")
    token = secrets.token_hex(16)
    get_redis().set(K_ADMIN_TOKEN.format(token), "1", ex=ADMIN_TOKEN_TTL)
    return {"username": ADMIN_USER, "name": "驿站管理员", "role": "admin", "token": token}


def check_admin_token(token: str) -> bool:
    if not token:
        return False
    return bool(get_redis().exists(K_ADMIN_TOKEN.format(token)))
