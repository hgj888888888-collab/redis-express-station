"""模块二：取件码与取件记录管理（必做）。

取件码设计：
  String + TTL   pickup:code:{code} -> 包裹ID   —— 取件码天然是「一次性、会失效的短字符串」，
                                                  用 String 存映射，并借助 TTL 让过期自动清理；
  String + TTL   parcel:{id}:code -> 取件码     —— 反向索引，便于前端展示「我的取件码」；
取件记录设计：
  List           user:{uid}:pickups             —— 最新取件记录 LPUSH 到表头，LTRIM 保留最近 50 条；
  Stream         pickup:stream                  —— 取件事件以追加日志形式写入，保留完整操作轨迹。
"""
import json
import random
import time
from typing import Any, Dict, List

from db import (
    BizError,
    K_BLACKLIST,
    K_CODE,
    K_CODE_USED,
    K_EXPIRE,
    K_LIGHT_SHELF,
    K_OVERDUE_ALERT,
    K_PARCEL,
    K_PARCEL_CODE,
    K_PICK_FAIL,
    K_PICK_STREAM,
    K_PICK_USERS,
    K_STATS_DAILY,
    K_STATS_STATUS,
    K_STATUS,
    K_STAY,
    K_USER_HISTORY,
    get_redis,
)
from settings import CODE_MAX_FAILS, CODE_TTL, FAIL_WINDOW, LIGHT_TTL, STATUS_PENDING, STATUS_PICKED
from serializers import to_history, to_parcel


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _now_text(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def generate_code(parcel_id: str, ttl: int = CODE_TTL) -> Dict[str, Any]:
    """为包裹生成 6 位取件码，使用 SET NX EX 保证码值唯一且自动过期。"""
    r = get_redis()
    key = K_PARCEL.format(parcel_id)
    h = r.hgetall(key)
    if not h:
        raise BizError("包裹不存在：%s" % parcel_id)
    if h.get("status") == STATUS_PICKED:
        raise BizError("该包裹已被取走，不能重复生成取件码")

    # 若已有未过期取件码，先清理旧映射，避免一个包裹对应多个有效码
    old = r.get(K_PARCEL_CODE.format(parcel_id))
    if old:
        r.delete(K_CODE.format(old))

    for _ in range(20):
        code = "%06d" % random.randint(0, 999999)
        if r.set(K_CODE.format(code), parcel_id, nx=True, ex=ttl):
            break
    else:
        raise BizError("取件码生成失败，请重试")

    expire_at = int(time.time()) + ttl
    pipe = r.pipeline(transaction=True)
    pipe.set(K_PARCEL_CODE.format(parcel_id), code, ex=ttl)
    pipe.hset(key, mapping={"pickup_code": code, "code_expire": expire_at})
    pipe.execute()
    return {
        "parcel_id": parcel_id,
        "code": code,
        "ttl": ttl,
        "expire_at": expire_at,
        "hint": "取件码 %d 天内有效，请勿泄露给他人" % (ttl // 86400),
    }


def get_code(parcel_id: str) -> Dict[str, Any]:
    """查询包裹当前取件码及其剩余有效期。"""
    r = get_redis()
    if not r.exists(K_PARCEL.format(parcel_id)):
        raise BizError("包裹不存在：%s" % parcel_id)
    code = r.get(K_PARCEL_CODE.format(parcel_id))
    if not code or not r.exists(K_CODE.format(code)):
        raise BizError("该包裹暂无有效取件码，请先生成")
    ttl = r.ttl(K_CODE.format(code))
    return {"parcel_id": parcel_id, "code": code, "ttl": ttl}


def light_shelf(parcel_id: str, ttl: int = LIGHT_TTL) -> Dict[str, Any]:
    """点亮包裹所在货架的指示灯。

    用 String + TTL 存「货架号 -> 包裹ID」，到期自动删除即灯自动熄灭，
    不需要额外的定时任务去关灯。
    """
    r = get_redis()
    h = r.hgetall(K_PARCEL.format(parcel_id))
    if not h:
        raise BizError("包裹不存在：%s" % parcel_id)
    if h.get("status") not in (STATUS_PENDING, "EXPIRED"):
        raise BizError("该包裹当前不可取件，无法点亮货架灯")

    shelf = h.get("shelf") or "未知货架"
    r.set(K_LIGHT_SHELF.format(shelf), parcel_id, ex=ttl)
    return {
        "parcel_id": parcel_id,
        "shelf": shelf,
        "ttl": ttl,
        "hint": "货架灯已点亮，请在 %d 秒内前往 %s" % (ttl, shelf),
    }


def _guard_attempts(r, ip: str) -> None:
    """取件码防爆破：同一来源在窗口期内错误次数达到上限则锁定。"""
    fails = int(r.get(K_PICK_FAIL.format(ip or "unknown")) or 0)
    if fails >= CODE_MAX_FAILS:
        left = int(r.ttl(K_PICK_FAIL.format(ip or "unknown")) or FAIL_WINDOW)
        raise BizError("取件码错误次数过多，请 %d 分钟后再试" % max(1, left // 60))


def _fail_once(r, ip: str) -> int:
    """累计一次错误，返回剩余可尝试次数。"""
    key = K_PICK_FAIL.format(ip or "unknown")
    fails = r.incr(key)
    if fails == 1:
        r.expire(key, FAIL_WINDOW)
    return max(0, CODE_MAX_FAILS - fails)


def verify_code(code: str, ip: str = "") -> Dict[str, Any]:
    """校验取件码并返回包裹信息（不改变状态），失败计入错误次数。"""
    r = get_redis()
    _guard_attempts(r, ip)
    pid = r.get(K_CODE.format(code))
    if not pid:
        left = _fail_once(r, ip)
        raise BizError("取件码不存在或已过期，还可尝试 %d 次" % left if left
                       else "取件码错误次数过多，请 10 分钟后再试")
    h = r.hgetall(K_PARCEL.format(pid))
    if not h:
        raise BizError("取件码对应包裹已被删除")
    r.delete(K_PICK_FAIL.format(ip or "unknown"))
    return to_parcel(pid, h)


def pickup(code: str, staff: str = "自助取件", ip: str = "") -> Dict[str, Any]:
    """取件核销：校验取件码 → 重复取件拦截 → 更新状态 → 写历史与事件流。

    加分功能「重复取件拦截」在此实现：状态机只允许 PENDING/EXPIRED -> PICKED，
    已取件包裹再次核销会被明确拒绝，避免一码多取。
    """
    r = get_redis()
    _guard_attempts(r, ip)
    pid = r.get(K_CODE.format(code))
    if not pid:
        # 取件码核销后会被删除，这里查短期保留的「已核销」标记，用于给出重复取件提示
        used_pid = r.get(K_CODE_USED.format(code))
        if used_pid:
            h = r.hgetall(K_PARCEL.format(used_pid))
            raise BizError("重复取件：该取件码已于 %s 使用，包裹已被取走" % h.get("picked_time_text", ""))
        left = _fail_once(r, ip)
        raise BizError("取件码不存在或已过期，还可尝试 %d 次" % left if left
                       else "取件码错误次数过多，请 10 分钟后再试")

    key = K_PARCEL.format(pid)
    h = r.hgetall(key)
    if not h:
        raise BizError("包裹不存在或已被删除")

    receiver_id = h.get("receiver_id", "")
    if r.sismember(K_BLACKLIST, receiver_id):
        raise BizError("该收件人已被限制取件，请联系驿站管理员")

    if h.get("status") == STATUS_PICKED:
        raise BizError("重复取件：该包裹已于 %s 取走" % h.get("picked_time_text", ""))
    if h.get("status") == "ABNORMAL":
        raise BizError("该包裹为异常件，请到柜台人工处理")

    now = int(time.time())
    now_text = _now_text(now)
    record = {
        "parcel_id": pid,
        "tracking_no": h.get("tracking_no", ""),
        "courier": h.get("courier", ""),
        "receiver_id": receiver_id,
        "receiver": h.get("receiver", ""),
        "station": h.get("station", ""),
        "shelf": h.get("shelf", ""),
        "pickup_time": now,
        "pickup_time_text": now_text,
        "staff": staff,
    }

    old_status = h.get("status", STATUS_PENDING)
    pipe = r.pipeline(transaction=True)
    pipe.hset(key, mapping={
        "status": STATUS_PICKED,
        "picked_time": now,
        "picked_time_text": now_text,
        "pickup_code": "",
    })
    # 取件码一次性使用，核销后立即删除，并保留 10 分钟的已用标记用于重复取件提示
    pipe.delete(K_CODE.format(code))
    pipe.set(K_CODE_USED.format(code), pid, ex=600)
    pipe.delete(K_PARCEL_CODE.format(pid))
    pipe.srem(K_STATUS.format(old_status), pid)
    pipe.sadd(K_STATUS.format(STATUS_PICKED), pid)
    # 已取件不再参与滞留排名、超期提醒与到期扫描
    pipe.zrem(K_STAY, pid)
    pipe.zrem(K_OVERDUE_ALERT, pid)
    pipe.zrem(K_EXPIRE, pid)
    # 取件成功，清空该来源的取件码错误计数
    pipe.delete(K_PICK_FAIL.format(ip or "unknown"))
    pipe.hincrby(K_STATS_STATUS, old_status, -1)
    pipe.hincrby(K_STATS_STATUS, STATUS_PICKED, 1)
    pipe.hincrby(K_STATS_DAILY.format(_today()), "picked", 1)
    # List：取件历史（最新在前，保留 50 条）
    pipe.lpush(K_USER_HISTORY.format(receiver_id), json.dumps(record, ensure_ascii=False))
    pipe.ltrim(K_USER_HISTORY.format(receiver_id), 0, 49)
    # HyperLogLog：去重统计取件用户数
    pipe.pfadd(K_PICK_USERS, receiver_id)
    # Stream：追加一条取件事件日志
    pipe.xadd(K_PICK_STREAM, {
        "parcel_id": pid,
        "receiver_id": receiver_id,
        "receiver": h.get("receiver", ""),
        "courier": h.get("courier", ""),
        "shelf": h.get("shelf", ""),
        "staff": staff,
        "time": now_text,
    }, maxlen=10000, approximate=True)
    pipe.execute()

    record["status"] = STATUS_PICKED
    record["status_text"] = "已取件"
    return record


def history_of_user(user_id: str) -> List[Dict[str, Any]]:
    r = get_redis()
    rows = r.lrange(K_USER_HISTORY.format(user_id), 0, 49)
    return [to_history(x) for x in rows]


def latest_events(count: int = 20) -> List[Dict[str, Any]]:
    """读取取件事件流（倒序）。"""
    r = get_redis()
    events = r.xrevrange(K_PICK_STREAM, count=count)
    result = []
    for event_id, fields in events:
        fields["event_id"] = event_id
        result.append(fields)
    return result
