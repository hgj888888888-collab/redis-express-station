"""接口自测脚本：按课程设计功能点逐项调用后端，打印结果。

用法（需先启动 app.py）：
    python test_api.py
"""
import json

import requests

BASE = "http://127.0.0.1:5000"


def show(title, resp):
    data = resp.json()
    flag = "OK " if data.get("ok") else "ERR"
    print("[%s] %-22s %s" % (flag, title, json.dumps(data.get("data", data.get("message")), ensure_ascii=False)[:160]))
    return data


def main():
    # 1. 入库
    resp = requests.post(BASE + "/api/parcels", json={
        "receiver_id": "20219001",
        "receiver": "测试同学",
        "phone": "138****0001",
        "courier": "顺丰",
        "tracking_no": "SF9000000001",
        "station": "菜鸟驿站·北区",
        "category": "数码",
        "shelf": "货架9号",
        "weight": 1.2,
        "ttl_days": 7,
    })
    d = show("包裹入库", resp)
    pid = d["data"]["id"]

    # 2. 查询
    show("包裹详情", requests.get(BASE + "/api/parcels/" + pid))
    show("用户包裹列表", requests.get(BASE + "/api/users/20219001/parcels"))
    show("按单号查询", requests.get(BASE + "/api/parcels/tracking/SF9000000001"))

    # 3. 取件码
    d = show("生成取件码", requests.post(BASE + "/api/parcels/" + pid + "/code", json={}))
    code = d["data"]["code"]
    show("查询取件码", requests.get(BASE + "/api/parcels/" + pid + "/code"))
    show("校验取件码", requests.post(BASE + "/api/pickup/verify", json={"code": code}))

    # 4. 取件 + 重复取件拦截
    show("取件核销", requests.post(BASE + "/api/pickup", json={"code": code, "staff": "自助取件"}))
    show("重复取件拦截（应失败）", requests.post(BASE + "/api/pickup", json={"code": code}))

    # 5. 取件历史 / 状态
    show("用户取件历史", requests.get(BASE + "/api/users/20219001/pickups"))
    show("包裹当前状态", requests.get(BASE + "/api/parcels/" + pid))

    # 6. 异常与删除
    d = show("异常标记", requests.post(BASE + "/api/parcels/" + pid + "/abnormal", json={"reason": "外包装破损"}))
    show("恢复待取", requests.post(BASE + "/api/parcels/" + pid + "/status", json={"status": "PENDING"}))
    show("删除包裹", requests.delete(BASE + "/api/parcels/" + pid))

    # 7. 排行统计
    show("用户包裹排行", requests.get(BASE + "/api/stats/rank/users?top=5"))
    show("滞留时长排行", requests.get(BASE + "/api/stats/rank/stay?top=5"))
    show("状态统计", requests.get(BASE + "/api/stats/status"))
    show("超期包裹", requests.get(BASE + "/api/stats/overdue?hours=48"))
    show("每日统计", requests.get(BASE + "/api/stats/daily?days=3"))
    show("去重取件人数", requests.get(BASE + "/api/stats/pickup-users"))

    # 8. 加分功能
    show("加入黑名单", requests.post(BASE + "/api/blacklist", json={"user_id": "20219999", "reason": "恶意拒收"}))
    show("黑名单列表", requests.get(BASE + "/api/blacklist"))
    show("黑名单用户入库（应失败）", requests.post(BASE + "/api/parcels", json={
        "receiver_id": "20219999", "receiver": "黑名单用户", "tracking_no": "SF0000000001"
    }))
    show("移出黑名单", requests.delete(BASE + "/api/blacklist/20219999"))

    show("取号排队", requests.post(BASE + "/api/queue", json={"user_id": "20219001"}))
    show("队列状态", requests.get(BASE + "/api/queue"))
    show("叫号", requests.post(BASE + "/api/queue/call", json={}))
    show("超期提醒生成", requests.post(BASE + "/api/remind/overdue", json={"hours": 48}))
    show("取件事件流", requests.get(BASE + "/api/events?count=3"))


if __name__ == "__main__":
    main()
