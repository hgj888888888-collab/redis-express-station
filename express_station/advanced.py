"""模块四：异常功能扩展（选做加分）。

包含四项扩展：
  1) 过期未取提醒：ZRangeByScore 扫描超期包裹，写入提醒 ZSet；
  2) 重复取件拦截：在 pickup() 中通过状态机判断，见 pickup.py；
  3) 黑名单机制：Set 存储，入库与取件双环节校验；
  4) 取件高峰队列：List 实现先进先出排队，配合 String 记录当前叫号。
"""
import time
from typing import Any, Dict, List

from db import (
    BizError,
    K_BLACKLIST,
    K_OVERDUE_ALERT,
    K_PARCEL,
    K_QUEUE,
    K_SERVING,
    K_SERVING_SHELF,
    K_USER_PARCELS,
    get_redis,
)
from settings import LIGHT_TTL, STATUS_EXPIRED, STATUS_PENDING
from stats import overdue_parcels
from pickup import light_shelf


# ---------------- 黑名单 ----------------
def add_blacklist(user_id: str, reason: str = "") -> Dict[str, Any]:
    if not user_id:
        raise BizError("用户账号不能为空")
    r = get_redis()
    r.sadd(K_BLACKLIST, user_id)
    return {"user_id": user_id, "reason": reason, "in_blacklist": True}


def remove_blacklist(user_id: str) -> Dict[str, Any]:
    r = get_redis()
    r.srem(K_BLACKLIST, user_id)
    return {"user_id": user_id, "in_blacklist": False}


def blacklist_users() -> List[str]:
    r = get_redis()
    return sorted(r.smembers(K_BLACKLIST))


def is_blacklisted(user_id: str) -> bool:
    return bool(get_redis().sismember(K_BLACKLIST, user_id))


# ---------------- 过期未取提醒 ----------------
def remind_overdue(hours: int = 48) -> Dict[str, Any]:
    """扫描滞留包裹：写入提醒集合，并把待取件状态迁移为超期未取。"""
    r = get_redis()
    rows = overdue_parcels(hours=hours)
    if not rows:
        return {"count": 0, "items": [], "hours": hours}

    pipe = r.pipeline(transaction=True)
    for item in rows:
        pipe.zadd(K_OVERDUE_ALERT, {item["id"]: item["inbound_time"]})
        pipe.hset(K_PARCEL.format(item["id"]), mapping={
            "status": STATUS_EXPIRED,
            "abnormal_reason": "滞留超过%d小时未取" % hours,
        })
        pipe.srem("parcels:status:PENDING", item["id"])
        pipe.sadd("parcels:status:EXPIRED", item["id"])
    pipe.hincrby("stats:status", "PENDING", -len(rows))
    pipe.hincrby("stats:status", "EXPIRED", len(rows))
    pipe.execute()
    return {"count": len(rows), "items": rows, "hours": hours, "remind_time": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------- 取件高峰队列 ----------------
def join_queue(user_id: str) -> Dict[str, Any]:
    """用户取号排队，返回当前排位（List 从队头到队尾为 RPUSH 顺序）。"""
    if not user_id:
        raise BizError("用户账号不能为空")
    r = get_redis()
    pos = r.lpos(K_QUEUE, user_id)
    if pos is None:
        r.rpush(K_QUEUE, user_id)
        pos = r.lpos(K_QUEUE, user_id)
    return {"user_id": user_id, "position": int(pos) + 1, "waiting": int(r.llen(K_QUEUE))}


def _pending_parcel_of(r, user_id: str) -> str:
    """找到该用户最早入库、仍未取件的包裹，用于叫号时点亮货架灯。"""
    best_id, best_ts = "", None
    for pid in r.smembers(K_USER_PARCELS.format(user_id)):
        h = r.hgetall(K_PARCEL.format(pid))
        if h.get("status") not in (STATUS_PENDING, STATUS_EXPIRED):
            continue
        ts = int(h.get("inbound_time") or 0)
        if best_ts is None or ts < best_ts:
            best_id, best_ts = pid, ts
    return best_id


def call_next() -> Dict[str, Any]:
    """工作人员叫号：弹出队头用户、记录当前叫号，并联动点亮其货架灯。"""
    r = get_redis()
    user_id = r.lpop(K_QUEUE)
    if not user_id:
        raise BizError("当前排队队列为空")
    r.set(K_SERVING, user_id)

    shelf, parcel_id, light_ttl = "", "", 0
    pid = _pending_parcel_of(r, user_id)
    if pid:
        info = light_shelf(pid, LIGHT_TTL)
        shelf, parcel_id, light_ttl = info["shelf"], pid, info["ttl"]
        r.set(K_SERVING_SHELF, shelf, ex=light_ttl)
    return {
        "serving": user_id,
        "shelf": shelf,
        "parcel_id": parcel_id,
        "light_ttl": light_ttl,
        "waiting": int(r.llen(K_QUEUE)),
    }


def queue_status() -> Dict[str, Any]:
    r = get_redis()
    serving = r.get(K_SERVING) or ""
    # 叫号时点亮的货架灯只有 120 秒 TTL，过期后 Key 消失；
    # 单独返回「该用户还有几件待取」，避免前端把「灯灭了」误显示成「没有待取包裹」。
    pending = 0
    if serving:
        for pid in r.smembers(K_USER_PARCELS.format(serving)):
            if (r.hget(K_PARCEL.format(pid), "status") or "") in (STATUS_PENDING, STATUS_EXPIRED):
                pending += 1
    return {
        "serving": serving,
        "serving_shelf": r.get(K_SERVING_SHELF) or "",
        "serving_ttl": r.ttl(K_SERVING_SHELF) if r.exists(K_SERVING_SHELF) else 0,
        "serving_pending": pending,
        "waiting": int(r.llen(K_QUEUE)),
        "list": r.lrange(K_QUEUE, 0, 19),
    }


def leave_queue(user_id: str) -> Dict[str, Any]:
    r = get_redis()
    removed = r.lrem(K_QUEUE, 0, user_id)
    return {"user_id": user_id, "removed": removed}
