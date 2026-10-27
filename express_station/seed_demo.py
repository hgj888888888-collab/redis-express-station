"""演示数据脚本：一键构造一批贴近真实业务的包裹、取件与超期数据。

用法：
    python seed_demo.py          # 写入演示数据（会先清空本库）
    python seed_demo.py --keep   # 不清空，追加数据
"""
import random
import sys
import time

import advanced
import parcel
import pickup
import stats
from db import get_redis
from settings import STATUS_PICKED

NAMES = ["张伟", "李娜", "王强", "刘洋", "陈晨", "赵敏", "孙悦", "周杰", "吴桐", "郑爽"]
COURIERS = ["顺丰", "中通", "圆通", "韵达", "京东", "邮政"]
CATEGORIES = ["普通件", "生鲜", "数码", "服饰", "文件", "大件"]
STATIONS = ["菜鸟驿站·北区", "菜鸟驿站·南区", "京东派·东门"]
PHONE_PREFIX = ["138", "139", "150", "158", "176", "188"]


def main():
    r = get_redis()
    if "--keep" not in sys.argv:
        r.flushdb()
        print("已清空当前 Redis 库")

    random.seed(2026)
    users = ["2021%04d" % i for i in range(1001, 1001 + 12)]
    created = []

    # 1. 批量入库（数量分布刻意不均，便于展示用户包裹数排名）
    # 学号与姓名一一对应，避免同一学号出现多个姓名
    for idx, uid in enumerate(users):
        count = random.randint(2, 9) if idx < 6 else random.randint(1, 3)
        for _ in range(count):
            courier = random.choice(COURIERS)
            item = parcel.add_parcel({
                "receiver_id": uid,
                "receiver": NAMES[idx % len(NAMES)],
                "phone": random.choice(PHONE_PREFIX) + "****" + str(random.randint(1000, 9999)),
                "courier": courier,
                "tracking_no": "%s%010d" % (courier[:2], random.randint(1, 999999)),
                "station": random.choice(STATIONS),
                "category": random.choice(CATEGORIES),
                "shelf": "货架%d号" % random.randint(1, 20),
                "weight": round(random.uniform(0.2, 12.0), 1),
                "ttl_days": random.choice([3, 5, 7]),
            })
            created.append(item)
    print("包裹入库完成：%d 件" % len(created))

    # 2. 模拟 60% 的包裹被取走
    picked = 0
    for item in created:
        if random.random() < 0.6 and item["status"] != STATUS_PICKED:
            code_info = pickup.generate_code(item["id"])
            try:
                pickup.pickup(code_info["code"], staff=random.choice(["自助取件", "驿站工作人员"]))
                picked += 1
            except Exception:
                pass
    print("已取件：%d 件" % picked)

    # 3. 让一部分包裹入库时间回拨，制造滞留与超期数据
    remain = [x for x in created if r.hget("parcel:%s" % x["id"], "status") == "PENDING"]
    for item in remain[: max(1, len(remain) // 3)]:
        back = random.randint(60, 200) * 3600
        ts = int(time.time()) - back
        r.hset("parcel:%s" % item["id"], "inbound_time", ts)
        r.zadd("parcels:stay", {item["id"]: ts})
    print("滞留数据构造完成：%d 件" % len(remain))

    # 4. 黑名单与排队演示数据
    advanced.add_blacklist(users[-1], "多次恶意拒收")
    for uid in users[:3]:
        advanced.join_queue(uid)

    print("\n--- 当前统计 ---")
    print("状态统计：", stats.status_stats())
    print("用户包裹数 Top5：", stats.rank_users(5))
    print("滞留时长 Top5：", [(x["id"], x["stay_hours"]) for x in stats.rank_stay(5)])
    print("超期未取（>48h）：", len(stats.overdue_parcels(48)))


if __name__ == "__main__":
    main()
