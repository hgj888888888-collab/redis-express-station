"""模块三：包裹排行与统计（选做加分）。

数据类型选型：
  ZSet    rank:user:parcels —— 用户包裹数量排名，ZINCRBY 维护分值，ZREVRANGE 直接取 TopN；
  ZSet    parcels:stay      —— score 为入库时间戳，越早入库 score 越小，天然是滞留时长榜；
  Hash    stats:status      —— 各状态计数，HGETALL 一次取回；
  Hash    stats:daily:*     —— 按天分桶统计入库量与取件量；
  HLL     stats:pickup_users—— 千万级用户去重计数只需 12KB 固定内存。
"""
import time
from typing import Any, Dict, List

from db import (
    K_OVERDUE_ALERT,
    K_PARCEL,
    K_PICK_USERS,
    K_RANK_USER,
    K_STATS_DAILY,
    K_STATS_STATUS,
    K_STAY,
    get_redis,
)
from settings import STATUS_PENDING, STATUS_TEXT
from serializers import to_parcel
from parcel import sweep_expired


def rank_users(top: int = 10) -> List[Dict[str, Any]]:
    """按用户包裹数量排行（ZSet 分值 = 包裹件数）。"""
    r = get_redis()
    rows = r.zrevrange(K_RANK_USER, 0, top - 1, withscores=True)
    return [
        {"user_id": uid, "parcel_count": int(score), "rank": idx + 1}
        for idx, (uid, score) in enumerate(rows)
    ]


def rank_stay(top: int = 10) -> List[Dict[str, Any]]:
    """按滞留时长排行（score 为入库时间戳，升序即为滞留最久）。"""
    r = get_redis()
    now = int(time.time())
    rows = r.zrange(K_STAY, 0, top - 1, withscores=True)
    result = []
    for idx, (pid, ts) in enumerate(rows):
        h = r.hgetall(K_PARCEL.format(pid))
        if not h:
            continue
        item = to_parcel(pid, h)
        stay_hours = round((now - int(ts)) / 3600, 1)
        item["stay_hours"] = stay_hours
        item["stay_text"] = "%d天%d小时" % (int(stay_hours // 24), int(stay_hours % 24))
        item["rank"] = idx + 1
        result.append(item)
    return result


def overdue_parcels(hours: int = 48, limit: int = 50) -> List[Dict[str, Any]]:
    """查询滞留超过指定小时数且仍未取件的包裹。"""
    r = get_redis()
    deadline = int(time.time()) - hours * 3600
    ids = r.zrangebyscore(K_STAY, "-inf", deadline, start=0, num=limit)
    now = int(time.time())
    result = []
    for pid in ids:
        h = r.hgetall(K_PARCEL.format(pid))
        if not h or h.get("status") != STATUS_PENDING:
            continue
        item = to_parcel(pid, h)
        item["stay_hours"] = round((now - int(h.get("inbound_time", now))) / 3600, 1)
        result.append(item)
    result.sort(key=lambda x: x["stay_hours"], reverse=True)
    return result


def status_stats() -> Dict[str, Any]:
    """各状态包裹数量统计。"""
    r = get_redis()
    raw = r.hgetall(K_STATS_STATUS)
    data = []
    total = 0
    for key, text in STATUS_TEXT.items():
        count = int(raw.get(key, 0))
        total += count
        data.append({"status": key, "status_text": text, "count": count})
    return {"total": total, "items": data}


def daily_stats(day: str = "") -> Dict[str, int]:
    """某天的入库量与取件量。"""
    r = get_redis()
    day = day or time.strftime("%Y-%m-%d")
    raw = r.hgetall(K_STATS_DAILY.format(day))
    return {"date": day, "inbound": int(raw.get("inbound", 0)), "picked": int(raw.get("picked", 0))}


def daily_recent(days: int = 7) -> List[Dict[str, Any]]:
    result = []
    now = int(time.time())
    for i in range(days - 1, -1, -1):
        day = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
        result.append(daily_stats(day))
    return result


def unique_pickup_users() -> int:
    """HyperLogLog 估算去重取件用户数。"""
    r = get_redis()
    return r.pfcount(K_PICK_USERS)


def overdue_alerts() -> List[Dict[str, Any]]:
    """超期提醒列表中尚未取件的包裹。"""
    r = get_redis()
    result = []
    for pid, ts in r.zrevrange(K_OVERDUE_ALERT, 0, 49, withscores=True):
        h = r.hgetall(K_PARCEL.format(pid))
        if not h or h.get("status") != STATUS_PENDING:
            continue
        item = to_parcel(pid, h)
        item["stay_hours"] = round((time.time() - int(ts)) / 3600, 1)
        result.append(item)
    return result


def dashboard_stats() -> Dict[str, Any]:
    """管理端数据看板：近 7 天出入库、状态分布、快递公司占比。

    快递公司占比用 SCAN 遍历包裹 Hash 现场聚合，避免额外维护一份索引；
    数据量增大时可改为 Hash 计数（HINCRBY stats:courier）增量维护。
    """
    r = get_redis()
    # 打开看板前先扫一遍到期件，保证「超期未取」数量是实时的
    sweep_expired()
    daily = daily_recent(7)
    status = status_stats()

    courier_counts: Dict[str, int] = {}
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, match="parcel:P*", count=200)
        for key in keys:
            # 跳过 parcel:P000001:code 这类附属 Key，只统计包裹 Hash
            pid = key[len("parcel:"):]
            if len(pid) < 2 or not pid[1:].isdigit():
                continue
            courier = r.hget(key, "courier") or "未知"
            courier_counts[courier] = courier_counts.get(courier, 0) + 1
        if cursor == 0:
            break
    couriers = [{"name": name, "count": count} for name, count in courier_counts.items()]
    couriers.sort(key=lambda x: x["count"], reverse=True)

    return {
        "daily": daily,
        "status": status,
        "couriers": couriers,
        "total": status["total"],
        "unique_pickup_users": unique_pickup_users(),
        "today": daily[-1] if daily else {"inbound": 0, "picked": 0, "date": ""},
    }
