"""站内到件通知：包裹入库后给收件人写入一条消息。

数据类型选型：
  List   notify:{uid}        —— 最新通知 LPUSH 到表头，LTRIM 只保留最近 50 条；
  String notify:{uid}:unread —— INCR 维护未读数，进入通知页后清零。

微信订阅消息需要真实 AppID 和模板 ID，游客模式下无法下发，
因此这里实现「站内通知」：用户打开小程序即可看到未读红点与消息列表。
"""
import json
import time
from typing import Any, Dict, List

from db import K_NOTIFY, K_NOTIFY_UNREAD, get_redis


def push_notify(user_id: str, title: str, content: str, kind: str = "inbound") -> None:
    """写入一条通知并累加未读数。"""
    if not user_id:
        return
    r = get_redis()
    now = int(time.time())
    payload = json.dumps({
        "title": title,
        "content": content,
        "kind": kind,
        "time": now,
        "time_text": time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
    }, ensure_ascii=False)
    pipe = r.pipeline(transaction=True)
    pipe.lpush(K_NOTIFY.format(user_id), payload)
    pipe.ltrim(K_NOTIFY.format(user_id), 0, 49)
    pipe.incr(K_NOTIFY_UNREAD.format(user_id))
    pipe.execute()


def list_for_user(user_id: str, limit: int = 20) -> Dict[str, Any]:
    """返回未读数与最近通知列表。"""
    r = get_redis()
    raw: List[str] = r.lrange(K_NOTIFY.format(user_id), 0, max(0, limit - 1))
    items = []
    for text in raw:
        try:
            items.append(json.loads(text))
        except ValueError:
            continue
    return {
        "unread": int(r.get(K_NOTIFY_UNREAD.format(user_id)) or 0),
        "items": items,
    }


def mark_read(user_id: str) -> Dict[str, Any]:
    """把用户未读数清零（打开通知页即视为已读）。"""
    r = get_redis()
    r.set(K_NOTIFY_UNREAD.format(user_id), 0)
    return {"user_id": user_id, "unread": 0}
