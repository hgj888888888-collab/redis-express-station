"""校园快递驿站管理系统 —— Flask API 入口。

启动：
    python app.py
默认监听 http://127.0.0.1:5000，微信开发者工具需勾选「不校验合法域名」。
"""
import os
import time

from flask import Flask, jsonify, request

import auth as auth_svc
import advanced
import notify as notify_svc
import parcel
import pickup as pickup_svc
import stats
from db import BizError
from settings import CODE_TTL, LIGHT_TTL, STATUS_TEXT

app = Flask(__name__)
app.json.ensure_ascii = False


@app.after_request
def _cors(resp):
    """开发阶段允许小程序 / 浏览器跨域调用。"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return resp


@app.errorhandler(BizError)
def _biz_error(exc):
    return jsonify({"ok": False, "message": str(exc)}), 400


@app.errorhandler(Exception)
def _server_error(exc):
    return jsonify({"ok": False, "message": "服务器内部错误：%s" % exc}), 500


def ok(data=None, message=""):
    return jsonify({"ok": True, "data": data, "message": message})


def body():
    return request.get_json(silent=True) or {}


def _client_ip() -> str:
    return (request.remote_addr or "").strip()


# ---------------- 鉴权守卫 ----------------
def _is_admin() -> bool:
    return auth_svc.check_admin_token(request.headers.get("X-Admin-Token", ""))


def require_admin() -> None:
    if not _is_admin():
        raise BizError("管理端登录已失效，请重新登录管理员账号")


# ---------------- 基础 ----------------
@app.get("/api/health")
def health():
    return ok({"time": int(time.time()), "status_text": STATUS_TEXT})


# ---------------- 登录与身份 ----------------
@app.post("/api/auth/login")
def login():
    d = body()
    return ok(auth_svc.admin_login(
        str(d.get("username", "")).strip(), str(d.get("password", ""))), "登录成功")


# ---------------- 模块一：包裹管理 ----------------
@app.post("/api/parcels")
def create_parcel():
    require_admin()
    return ok(parcel.add_parcel(body()), "包裹入库成功")


@app.get("/api/parcels")
def list_parcels():
    user_id = request.args.get("user_id") or None
    if not user_id:
        require_admin()
    return ok(parcel.list_parcels(
        status=request.args.get("status") or None,
        user_id=user_id,
        limit=int(request.args.get("limit", 200)),
    ))


@app.get("/api/parcels/<pid>")
def parcel_detail(pid):
    return ok(parcel.get_parcel(pid))


@app.get("/api/parcels/tracking/<tracking_no>")
def parcel_by_tracking(tracking_no):
    require_admin()
    return ok(parcel.query_by_tracking(tracking_no))


@app.post("/api/parcels/<pid>/status")
def update_status(pid):
    require_admin()
    d = body()
    return ok(parcel.update_status(pid, d.get("status", "PENDING"), d.get("reason", "")), "状态已更新")


@app.post("/api/parcels/<pid>/abnormal")
def mark_abnormal(pid):
    require_admin()
    return ok(parcel.mark_abnormal(pid, body().get("reason", "")), "已标记为异常件")


@app.post("/api/parcels/<pid>/refuse")
def refuse_parcel(pid):
    return ok(parcel.refuse_parcel(pid, body().get("reason", "")), "已拒收")


@app.post("/api/parcels/<pid>/return")
def return_parcel(pid):
    return ok(parcel.return_parcel(pid, body().get("reason", "")), "已退货")


@app.post("/api/parcels/<pid>/restore")
def restore_refused(pid):
    require_admin()
    return ok(parcel.restore_refused(pid), "已撤销拒收，恢复正常待取件")


@app.post("/api/parcels/<pid>/origin")
def send_back_origin(pid):
    require_admin()
    return ok(parcel.send_back_origin(pid, body().get("reason", "")), "已发回发出地")


@app.delete("/api/parcels/<pid>")
def delete_parcel(pid):
    require_admin()
    return ok(parcel.delete_parcel(pid), "包裹已删除")


# ---------------- 超期件处置 ----------------
@app.post("/api/parcels/expired/sweep")
def sweep_expired():
    require_admin()
    return ok(parcel.sweep_expired(), "超期扫描完成")


@app.post("/api/parcels/expired/return")
def return_expired():
    require_admin()
    d = body()
    reason = d.get("reason") or "超期未取，退回快递公司"
    return ok(parcel.return_expired(d.get("ids") or [], reason), "超期件已退回")


# ---------------- 模块二：取件码与取件 ----------------
@app.post("/api/parcels/<pid>/code")
def create_code(pid):
    d = body()
    return ok(pickup_svc.generate_code(pid, int(d.get("ttl", CODE_TTL))), "取件码生成成功")


@app.get("/api/parcels/<pid>/code")
def query_code(pid):
    return ok(pickup_svc.get_code(pid))


@app.post("/api/parcels/<pid>/light")
def light_shelf(pid):
    d = body()
    return ok(pickup_svc.light_shelf(pid, int(d.get("ttl", LIGHT_TTL))), "货架灯已点亮")


@app.post("/api/pickup/verify")
def verify_code():
    return ok(pickup_svc.verify_code(str(body().get("code", "")), _client_ip()))


@app.post("/api/pickup")
def do_pickup():
    d = body()
    return ok(pickup_svc.pickup(
        str(d.get("code", "")), d.get("staff", "自助取件"), _client_ip()), "取件成功")


@app.get("/api/users/<uid>/parcels")
def user_parcels(uid):
    return ok(parcel.list_parcels(user_id=uid))


@app.get("/api/users/<uid>/pickups")
def user_history(uid):
    return ok(pickup_svc.history_of_user(uid))


@app.get("/api/users/<uid>/notifications")
def user_notifications(uid):
    return ok(notify_svc.list_for_user(uid, int(request.args.get("limit", 20))))


@app.post("/api/users/<uid>/notifications/read")
def read_notifications(uid):
    return ok(notify_svc.mark_read(uid), "已读")


@app.get("/api/events")
def events():
    require_admin()
    return ok(pickup_svc.latest_events(int(request.args.get("count", 20))))


# ---------------- 模块三：排行与统计 ----------------
@app.get("/api/stats/rank/users")
def rank_users():
    require_admin()
    return ok(stats.rank_users(int(request.args.get("top", 10))))


@app.get("/api/stats/rank/stay")
def rank_stay():
    require_admin()
    return ok(stats.rank_stay(int(request.args.get("top", 10))))


@app.get("/api/stats/overdue")
def overdue():
    require_admin()
    return ok(stats.overdue_parcels(int(request.args.get("hours", 48))))


@app.get("/api/stats/status")
def status_stats():
    require_admin()
    return ok(stats.status_stats())


@app.get("/api/stats/dashboard")
def dashboard():
    """管理端数据看板：近 7 天出入库 + 状态分布 + 快递公司占比。"""
    require_admin()
    return ok(stats.dashboard_stats())


@app.get("/api/stats/daily")
def daily_stats():
    require_admin()
    if request.args.get("days"):
        return ok(stats.daily_recent(int(request.args.get("days"))))
    return ok(stats.daily_stats(request.args.get("date", "")))


@app.get("/api/stats/pickup-users")
def pickup_users():
    require_admin()
    return ok({"unique_users": stats.unique_pickup_users()})


@app.get("/api/stats/overview")
def overview():
    """首页概览：状态统计 + 今日数据 + 去重取件人数。"""
    require_admin()
    parcel.sweep_expired()  # 打开管理页前先同步一次超期状态
    return ok({
        "status": stats.status_stats(),
        "today": stats.daily_stats(),
        "unique_users": stats.unique_pickup_users(),
        "alerts": len(stats.overdue_alerts()),
    })


# ---------------- 模块四：异常扩展 ----------------
@app.get("/api/blacklist")
def blacklist_list():
    require_admin()
    return ok(advanced.blacklist_users())


@app.post("/api/blacklist")
def blacklist_add():
    require_admin()
    d = body()
    return ok(advanced.add_blacklist(str(d.get("user_id", "")), d.get("reason", "")), "已加入黑名单")


@app.delete("/api/blacklist/<uid>")
def blacklist_remove(uid):
    require_admin()
    return ok(advanced.remove_blacklist(uid), "已移出黑名单")


@app.post("/api/remind/overdue")
def remind_overdue():
    require_admin()
    return ok(advanced.remind_overdue(int(body().get("hours", 48))), "超期提醒已生成")


@app.get("/api/queue")
def queue_status():
    return ok(advanced.queue_status())


@app.post("/api/queue")
def queue_join():
    uid = str(body().get("user_id", ""))
    return ok(advanced.join_queue(uid), "排队成功")


@app.delete("/api/queue")
def queue_leave():
    uid = str(body().get("user_id", ""))
    return ok(advanced.leave_queue(uid), "已退出排队")


@app.post("/api/queue/call")
def queue_call():
    require_admin()
    return ok(advanced.call_next(), "已叫号")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
