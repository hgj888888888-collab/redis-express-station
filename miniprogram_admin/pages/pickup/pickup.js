const api = require("../../utils/api");

Page({
  data: {
    code: "",
    result: null,
    history: [],
    queue: null,
    myQueuePos: 0,
    userId: ""
  },

  onShow() {
    const app = getApp();
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setData({ selected: 1, role: app.globalData.role });
    }
    const uid = app.globalData.userId;
    this.setData({ userId: uid });
    this.loadHistory(uid);
    this.loadQueue();
    this.startQueueTimer();
  },

  onHide() {
    clearInterval(this._queueTimer);
  },

  onUnload() {
    clearInterval(this._queueTimer);
  },

  // 叫号 / 货架灯由管理端触发，用户端每 5 秒拉一次排队状态
  startQueueTimer() {
    clearInterval(this._queueTimer);
    this._queueTimer = setInterval(() => this.loadQueue(), 5000);
  },

  loadHistory(uid) {
    if (!uid) return;
    api.get("/api/users/" + uid + "/pickups").then((list) => {
      this.setData({
        history: list.map((x) => ({
          ...x,
          timeText: x.pickup_time_text || api.fmtTime(x.pickup_time)
        }))
      });
    });
  },

  loadQueue() {
    api.get("/api/queue").then((q) => {
      const idx = (q.list || []).indexOf(this.data.userId);
      this.setData({ queue: q, myQueuePos: idx >= 0 ? idx + 1 : 0 });
    });
  },

  onCodeInput(e) {
    this.setData({ code: e.detail.value.replace(/\D/g, "").slice(0, 6), result: null });
  },

  submit() {
    const code = this.data.code;
    if (code.length !== 6) {
      wx.showToast({ title: "请输入 6 位取件码", icon: "none" });
      return;
    }
    api
      .post("/api/pickup", { code: code, staff: "自助取件" })
      .then((r) => {
        this.setData({ result: r, code: "" });
        wx.vibrateShort({ type: "light" });
        this.loadHistory(r.receiver_id);
        this.loadQueue();
      })
      .catch(() => {});
  },

  joinQueue() {
    api.post("/api/queue", { user_id: this.data.userId }).then((r) => {
      this.setData({ myQueuePos: r.position });
      this.loadQueue();
      wx.showToast({ title: "已取号，前方 " + (r.position - 1) + " 人", icon: "none" });
    });
  },

  leaveQueue() {
    api.del("/api/queue", { user_id: this.data.userId }).then(() => {
      this.setData({ myQueuePos: 0 });
      this.loadQueue();
      wx.showToast({ title: "已退出排队", icon: "none" });
    });
  },

  onPullDownRefresh() {
    this.loadQueue();
    wx.stopPullDownRefresh();
  }
});
