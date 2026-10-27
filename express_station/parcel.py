"""模块一：包裹信息管理（必做）。

Redis 数据类型选型：
  Hash            parcel:{id}        —— 包裹是一条结构不固定、字段可增删的记录，Hash 最贴合；
  Set             user:{uid}:parcels —— 一个用户的多条包裹，Set 天然去重；
  Set             parcels:status:*   —— 按状态分组索引，实现状态快速筛选；
  ZSet(score=入库时间) parcels:stay   —— 支持按滞留时长排序；
  Hash            stats:status       —— HINCRBY 原子累加各状态计数；
  String          parcel:id          —— INCR 生成自增包裹号。
"""
import time
from typing import Any, Dict, List, Optional

from db import (
    BizError,
    K_BLACKLIST,
    K_CODE,
    K_EXPIRE,
    K_OVERDUE_ALERT,
    K_PARCEL,
    K_PARCEL_CODE,
    K_PARCEL_EVENTS,
    K_PARCEL_SEQ,
    K_RANK_USER,
    K_STATS_DAILY,
    K_STATS_STATUS,
    K_STATUS,
    K_STAY,
    K_TRACKING,
    K_USER_PARCELS,
    get_redis,
)
from settings import (
    COURIER_PREFIX,
    CODE_TTL,
    STATUS_ABNORMAL,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_PICKED,
    STATUS_REFUSED,
    STATUS_RETURNED,
    STATUS_TEXT,
)
from pickup import generate_code
from notify import push_notify
from serializers import to_parcel


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _tx_pipeline(r):
    """使用事务管道保证「包裹 Hash 与各索引」同批次提交。"""
    return r.pipeline(transaction=True)


def add_parcel(data: Dict[str, Any]) -> Dict[str, Any]:
    """包裹入库：写入 Hash 并同步维护各类索引。"""
    receiver_id = str(data.get("receiver_id", "")).strip()
    receiver = str(data.get("receiver", "")).strip()
    if not receiver_id or not receiver:
        raise BizError("收件人账号和姓名不能为空")

    r = get_redis()
    if r.sismember(K_BLACKLIST, receiver_id):
        raise BizError("该用户已被列入黑名单，无法入库")

    courier = str(data.get("courier", "顺丰")).strip()
    tracking_no = str(data.get("tracking_no", "")).strip()
    if not tracking_no:
        raise BizError("快递单号不能为空")

    # INCR 生成包裹自增 ID
    seq = r.incr(K_PARCEL_SEQ)
    parcel_id = "P%06d" % seq

    # 单号唯一约束：SET NX 抢占「单号 -> 包裹ID」索引，抢不到说明已入库
    tracking_key = K_TRACKING.format(tracking_no)
    if not r.set(tracking_key, parcel_id, nx=True):
        exist = r.get(tracking_key) or ""
        exist_hash = r.hgetall(K_PARCEL.format(exist)) if exist else {}
        if exist_hash:
            raise BizError("该快递单号已入库：%s（%s）" % (
                exist, STATUS_TEXT.get(exist_hash.get("status", ""), "未知状态")))
        r.set(tracking_key, parcel_id)  # 索引指向已删除包裹，清理后重新占用

    now = int(time.time())
    ttl_days = int(data.get("ttl_days", 7))
    expire_time = now + ttl_days * 86400
    shelf = str(data.get("shelf") or ("货架" + str(seq % 20 + 1) + "号"))
    record = {
        "id": parcel_id,
        "tracking_no": tracking_no,
        "courier": courier,
        "prefix": COURIER_PREFIX.get(courier, tracking_no[:2].upper()),
        "receiver_id": receiver_id,
        "receiver": receiver,
        "phone": str(data.get("phone", "")).strip(),
        "station": str(data.get("station", "菜鸟驿站·北区")),
        "category": str(data.get("category", "普通件")),
        "shelf": shelf,
        "weight": float(data.get("weight", 0.5) or 0.5),
        "status": STATUS_PENDING,
        "inbound_time": str(now),
        "expire_time": str(expire_time),
        "pickup_code": "",
        "picked_time": "",
        "abnormal_reason": "",
    }

    key = K_PARCEL.format(parcel_id)
    pipe = _tx_pipeline(r)
    pipe.hset(key, mapping=record)
    pipe.sadd(K_USER_PARCELS.format(receiver_id), parcel_id)
    pipe.sadd(K_STATUS.format(STATUS_PENDING), parcel_id)
    # score 为入库时间戳：分值为数字，直接按 "滞留时长 = 当前时间 - 入库时间" 排序
    pipe.zadd(K_STAY, {parcel_id: now})
    # score 为保管到期时间：ZRANGEBYSCORE -inf now 即可批量捞出所有到期包裹
    pipe.zadd(K_EXPIRE, {parcel_id: expire_time})
    pipe.hincrby(K_STATS_STATUS, STATUS_PENDING, 1)
    pipe.hincrby(K_STATS_DAILY.format(_today()), "inbound", 1)
    # ZSet：用户包裹数量排行，入库即 +1 分
    pipe.zincrby(K_RANK_USER, 1, receiver_id)
    pipe.execute()

    # 入库即生成取件码：有效期与包裹保管期一致，用户打开小程序即可看到
    try:
        info = generate_code(parcel_id, ttl=ttl_days * 86400)
        record["pickup_code"] = info["code"]
    except BizError:
        pass  # 生成失败不阻断入库，用户仍可在详情页重新获取

    # 站内到件通知：用户下次打开小程序即可看到未读红点
    push_notify(
        receiver_id,
        "包裹已到站",
        "您的%s包裹已到达%s，货架 %s%s，请在 %d 天内取件。" % (
            courier, record["station"], shelf,
            "，取件码 %s" % record["pickup_code"] if record["pickup_code"] else "",
            ttl_days,
        ),
    )
    return to_parcel(parcel_id, record)


def get_parcel(parcel_id: str) -> Dict[str, Any]:
    r = get_redis()
    # 惰性超期判定：读到待取件且已过期的包裹则自动置为超期
    _refresh_expire(r, parcel_id)
    h = r.hgetall(K_PARCEL.format(parcel_id))
    if not h:
        raise BizError("包裹不存在：%s" % parcel_id)
    return to_parcel(parcel_id, h)


def query_by_tracking(tracking_no: str) -> List[Dict[str, Any]]:
    """按快递单号查询（此处在包裹 ID 空间内做扫描匹配，演示 SCAN 用法）。"""
    r = get_redis()
    result = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, match="parcel:P*", count=200)
        for key in keys:
            h = r.hgetall(key)
            if h.get("tracking_no") == tracking_no:
                result.append(to_parcel(key.split(":")[1], h))
        if cursor == 0:
            break
    if not result:
        raise BizError("未找到单号对应的包裹：%s" % tracking_no)
    return result


def get_parcel_by_code(code: str) -> Dict[str, Any]:
    r = get_redis()
    pid = r.get(K_CODE.format(code))
    if not pid:
        raise BizError("取件码不存在或已过期，请重新生成")
    return get_parcel(pid)


def list_parcels(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    r = get_redis()
    if user_id:
        ids = list(r.smembers(K_USER_PARCELS.format(user_id)))
    elif status:
        ids = list(r.smembers(K_STATUS.format(status)))
    else:
        ids = list(r.smembers(K_STATUS.format(STATUS_PENDING)))
        ids += list(r.smembers(K_STATUS.format(STATUS_EXPIRED)))

    rows = []
    for pid in ids[:limit]:
        _refresh_expire(r, pid)
        h = r.hgetall(K_PARCEL.format(pid))
        if not h:
            continue
        if status and h.get("status") != status:
            continue
        rows.append(to_parcel(pid, h))
    rows.sort(key=lambda x: x["inbound_time"], reverse=True)
    return rows


def _mark_expired(r, parcel_id: str, h: Dict[str, Any]) -> None:
    """待取件 -> 超期未取：维护状态索引、计数、超期提醒，并推送站内通知。"""
    now = int(time.time())
    pipe = _tx_pipeline(r)
    pipe.hset(K_PARCEL.format(parcel_id), "status", STATUS_EXPIRED)
    pipe.srem(K_STATUS.format(STATUS_PENDING), parcel_id)
    pipe.sadd(K_STATUS.format(STATUS_EXPIRED), parcel_id)
    pipe.hincrby(K_STATS_STATUS, STATUS_PENDING, -1)
    pipe.hincrby(K_STATS_STATUS, STATUS_EXPIRED, 1)
    # 已超期：移出「到期扫描」索引，转入超期提醒榜
    pipe.zrem(K_EXPIRE, parcel_id)
    pipe.zadd(K_OVERDUE_ALERT, {parcel_id: int(h.get("inbound_time") or now)})
    pipe.execute()
    push_notify(
        h.get("receiver_id", ""),
        "包裹已超期未取",
        "您的%s包裹在 %s 已超过免费保管期，请尽快取件或联系驿站处理。" % (
            h.get("courier", ""), h.get("shelf", "")),
        kind="expire",
    )


def _refresh_expire(r, parcel_id: str) -> None:
    """读取时惰性判定：待取件且已过保管期则迁移为超期未取。"""
    key = K_PARCEL.format(parcel_id)
    if r.hget(key, "status") != STATUS_PENDING:
        return
    expire_time = int(r.hget(key, "expire_time") or 0)
    if expire_time and expire_time < int(time.time()):
        _mark_expired(r, parcel_id, r.hgetall(key) or {})


def sweep_expired(limit: int = 500) -> Dict[str, Any]:
    """批量扫描已到期的待取件包裹（替代数据库里的定时任务）。

    ZSet 的 score 就是保管到期时间，ZRANGEBYSCORE -inf now 一次取出全部到期件，
    不需要逐条 SCAN，复杂度 O(logN + M)。
    """
    r = get_redis()
    now = int(time.time())
    ids = r.zrangebyscore(K_EXPIRE, "-inf", now, start=0, num=limit)
    changed = 0
    for pid in ids:
        h = r.hgetall(K_PARCEL.format(pid))
        if h and h.get("status") == STATUS_PENDING:
            _mark_expired(r, pid, h)
            changed += 1
        else:
            r.zrem(K_EXPIRE, pid)  # 已取件 / 已删除的索引残留清理
    return {"checked": len(ids), "expired": changed}


def return_expired(parcel_ids: Optional[List[str]] = None,
                   reason: str = "超期未取，退回快递公司") -> Dict[str, Any]:
    """超期件处置：把超期未取件批量退回快递公司，补齐「超期 -> 退回」闭环。"""
    r = get_redis()
    ids = [str(x) for x in (parcel_ids or [])]
    if not ids:
        ids = list(r.smembers(K_STATUS.format(STATUS_EXPIRED)))[:200]
    done = []
    skipped = 0
    for pid in ids:
        h = r.hgetall(K_PARCEL.format(pid))
        if not h or h.get("status") != STATUS_EXPIRED:
            skipped += 1
            continue
        _close_delivery(pid, STATUS_RETURNED, "expire_return", reason, reason)
        done.append(pid)
    return {"count": len(done), "skipped": skipped, "ids": done}


def update_status(parcel_id: str, status: str, reason: str = "") -> Dict[str, Any]:
    """状态更新 / 异常标记：同步维护状态索引集合与状态统计 Hash。"""
    r = get_redis()
    key = K_PARCEL.format(parcel_id)
    old = r.hget(key, "status")
    if not old:
        raise BizError("包裹不存在：%s" % parcel_id)

    field = {"reason": reason, "abnormal_reason": reason} if reason else {}
    field["status"] = status
    pipe = _tx_pipeline(r)
    pipe.hset(key, mapping=field)
    pipe.srem(K_STATUS.format(old), parcel_id)
    pipe.sadd(K_STATUS.format(status), parcel_id)
    pipe.hincrby(K_STATS_STATUS, old, -1)
    pipe.hincrby(K_STATS_STATUS, status, 1)
    pipe.execute()
    return get_parcel(parcel_id)


def mark_abnormal(parcel_id: str, reason: str) -> Dict[str, Any]:
    return update_status(parcel_id, STATUS_ABNORMAL, reason or "人工标记异常")


def _close_delivery(parcel_id: str, new_status: str, action: str,
                    reason: str, default_reason: str) -> Dict[str, Any]:
    """拒收 / 退货的公共处理：迁移状态、清理取件码与等待队列索引、记录事件流。"""
    r = get_redis()
    key = K_PARCEL.format(parcel_id)
    h = r.hgetall(key)
    if not h:
        raise BizError("包裹不存在：%s" % parcel_id)
    old = h.get("status", STATUS_PENDING)
    if old == new_status:
        raise BizError("该包裹已是%s状态" % STATUS_TEXT.get(new_status, new_status))

    now = int(time.time())
    now_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
    reason = reason or default_reason
    field_prefix = "refused" if new_status == STATUS_REFUSED else "return"
    reason_text = reason or default_reason

    pipe = _tx_pipeline(r)
    pipe.hset(key, mapping={
        "status": new_status,
        field_prefix + "_reason": reason_text,
        field_prefix + "_time": str(now),
        field_prefix + "_time_text": now_text,
        "pickup_code": "",
    })
    pipe.srem(K_STATUS.format(old), parcel_id)
    pipe.sadd(K_STATUS.format(new_status), parcel_id)
    pipe.hincrby(K_STATS_STATUS, old, -1)
    pipe.hincrby(K_STATS_STATUS, new_status, 1)
    # 不再参与滞留排行、超期提醒与到期扫描
    pipe.zrem(K_STAY, parcel_id)
    pipe.zrem(K_OVERDUE_ALERT, parcel_id)
    pipe.zrem(K_EXPIRE, parcel_id)
    # 取件码立即失效，避免拒收/退货后仍能取件
    if h.get("pickup_code"):
        pipe.delete(K_CODE.format(h["pickup_code"]))
    pipe.delete(K_PARCEL_CODE.format(parcel_id))
    # Stream：记录拒收 / 退货事件，便于追溯
    pipe.xadd(K_PARCEL_EVENTS, {
        "parcel_id": parcel_id,
        "action": action,
        "reason": reason_text,
        "receiver_id": h.get("receiver_id", ""),
        "receiver": h.get("receiver", ""),
        "shelf": h.get("shelf", ""),
        "time": now_text,
    }, maxlen=10000, approximate=True)
    pipe.execute()
    return get_parcel(parcel_id)


def refuse_parcel(parcel_id: str, reason: str = "") -> Dict[str, Any]:
    """收件人拒收：待取件/超期件 → 已拒收，包裹退回快递公司。"""
    r = get_redis()
    old = r.hget(K_PARCEL.format(parcel_id), "status")
    if old not in (STATUS_PENDING, STATUS_EXPIRED):
        raise BizError("只有待取件或超期未取的包裹才能拒收")
    return _close_delivery(parcel_id, STATUS_REFUSED, "refuse", reason, "收件人拒收")


def return_parcel(parcel_id: str, reason: str = "") -> Dict[str, Any]:
    """已取件退货：已取件 → 已退货，记录退货原因。"""
    r = get_redis()
    old = r.hget(K_PARCEL.format(parcel_id), "status")
    if old != STATUS_PICKED:
        raise BizError("只有已取件的包裹才能申请退货")
    return _close_delivery(parcel_id, STATUS_RETURNED, "return", reason, "七天无理由退货")


def send_back_origin(parcel_id: str, reason: str = "") -> Dict[str, Any]:
    """拒收件发回发出地：已拒收 → 已退货，登记退回寄件地的原因。"""
    r = get_redis()
    old = r.hget(K_PARCEL.format(parcel_id), "status")
    if old != STATUS_REFUSED:
        raise BizError("只有已拒收的包裹才能发回发出地")
    return _close_delivery(parcel_id, STATUS_RETURNED, "return", reason, "拒收，原路退回发出地")


def restore_refused(parcel_id: str) -> Dict[str, Any]:
    """撤销拒收：已拒收 → 待取件，重新生成取件码，恢复滞留索引。"""
    r = get_redis()
    key = K_PARCEL.format(parcel_id)
    h = r.hgetall(key)
    if not h:
        raise BizError("包裹不存在：%s" % parcel_id)
    if h.get("status") != STATUS_REFUSED:
        raise BizError("只有已拒收的包裹才能撤销拒收")

    now = int(time.time())
    pipe = _tx_pipeline(r)
    pipe.hset(key, mapping={
        "status": STATUS_PENDING,
        "expire_time": str(now + CODE_TTL),
        "pickup_code": "",
        "refused_reason": "",
        "refused_time": "",
        "refused_time_text": "",
    })
    pipe.srem(K_STATUS.format(STATUS_REFUSED), parcel_id)
    pipe.sadd(K_STATUS.format(STATUS_PENDING), parcel_id)
    pipe.hincrby(K_STATS_STATUS, STATUS_REFUSED, -1)
    pipe.hincrby(K_STATS_STATUS, STATUS_PENDING, 1)
    pipe.zadd(K_STAY, {parcel_id: int(h.get("inbound_time") or now)})
    pipe.zadd(K_EXPIRE, {parcel_id: now + CODE_TTL})
    pipe.zrem(K_OVERDUE_ALERT, parcel_id)
    pipe.execute()

    try:
        generate_code(parcel_id, ttl=CODE_TTL)
    except BizError:
        pass
    return get_parcel(parcel_id)


def delete_parcel(parcel_id: str) -> Dict[str, Any]:
    """删除包裹：清理 Hash 与所有关联索引（Set/ZSet/统计）。"""
    r = get_redis()
    key = K_PARCEL.format(parcel_id)
    h = r.hgetall(key)
    if not h:
        raise BizError("包裹不存在：%s" % parcel_id)
    status = h.get("status", STATUS_PENDING)
    receiver_id = h.get("receiver_id", "")

    pipe = _tx_pipeline(r)
    pipe.delete(key)
    pipe.delete(K_PARCEL_CODE.format(parcel_id))
    if h.get("tracking_no"):
        pipe.delete(K_TRACKING.format(h["tracking_no"]))
    if h.get("pickup_code"):
        pipe.delete(K_CODE.format(h["pickup_code"]))
    pipe.srem(K_USER_PARCELS.format(receiver_id), parcel_id)
    pipe.srem(K_STATUS.format(status), parcel_id)
    pipe.zrem(K_STAY, parcel_id)
    pipe.zrem(K_EXPIRE, parcel_id)
    pipe.zrem(K_OVERDUE_ALERT, parcel_id)
    pipe.hincrby(K_STATS_STATUS, status, -1)
    pipe.execute()
    return {"id": parcel_id, "deleted": True}
