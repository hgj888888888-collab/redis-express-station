"""序列化工具：把 Redis 中存储的「非结构化数据」转换为前端易用的结构。"""
import json
from typing import Any, Dict

from settings import STATUS_TEXT


def _f(h: Dict[str, Any], key: str, default: Any = "") -> Any:
    value = h.get(key)
    return default if value is None or value == "" else value


def to_parcel(pid: str, h: Dict[str, Any]) -> Dict[str, Any]:
    """把包裹 Hash 转成对外的 JSON 结构。"""
    status = _f(h, "status", "PENDING")
    return {
        "id": pid,
        "courier": _f(h, "courier"),
        "tracking_no": _f(h, "tracking_no"),
        "receiver": _f(h, "receiver"),
        "phone": _f(h, "phone"),
        "station": _f(h, "station"),
        "category": _f(h, "category"),
        "shelf": _f(h, "shelf"),
        "weight": float(_f(h, "weight", 0)),
        "inbound_time": int(_f(h, "inbound_time", 0)),
        "status": status,
        "status_text": STATUS_TEXT.get(status, status),
        "expire_time": int(_f(h, "expire_time", 0)),
        "pickup_code": _f(h, "pickup_code"),
        "picked_time": int(_f(h, "picked_time", 0)),
        "abnormal_reason": _f(h, "abnormal_reason"),
        "refused_reason": _f(h, "refused_reason"),
        "refused_time_text": _f(h, "refused_time_text"),
        "return_reason": _f(h, "return_reason"),
        "return_time_text": _f(h, "return_time_text"),
    }


def to_history(raw: str) -> Dict[str, Any]:
    """用户取件历史以 JSON 字符串存储在 List 中，这里反序列化。"""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = {"raw": raw}
    data.setdefault("pickup_time_text", "")
    return data
