const api = require("../../utils/api");

const COURIERS = ["顺丰", "中通", "圆通", "韵达", "京东", "邮政"];
const CATEGORIES = ["普通件", "生鲜", "数码", "服饰", "文件", "大件"];
const STATIONS = ["菜鸟驿站·北区", "菜鸟驿站·南区", "京东派·东门"];

const TAG_MAP = {
  PENDING: "tag-pending",
  PICKED: "tag-picked",
  EXPIRED: "tag-expired",
  ABNORMAL: "tag-abnormal",
  REFUSED: "tag-refused",
  RETURNED: "tag-returned"
};

// 快递单号前缀 -> 快递公司，扫码后自动选择
const PREFIX_RULES = [
  ["ZTO", "中通"],
  ["YTO", "圆通"],
  ["SF", "顺丰"],
  ["YD", "韵达"],
  ["JD", "京东"],
  ["EMS", "邮政"],
  ["YZ", "邮政"]
];

Page({
  data: {
    couriers: COURIERS,
    categories: CATEGORIES,
    stations: STATIONS,
    courierIndex: 0,
    categoryIndex: 0,
    stationIndex: 0,
    form: {
      receiver_id: "20211003",
      receiver: "张伟",
      phone: "",
      tracking_no: "",
      shelf: "",
      weight: "0.5",
      ttl_days: "7"
    },
    queryKey: "",
    current: null,
    currentTag: "",
    overview: null,
    expiredCount: 0,
    sweeping: false,
    queue: null,
    reminding: false,
    events: [],
    blacklist: [],
    newBlack: "",
    abnormalReason: "外包装破损"
  },

  onShow() {
    // 管理后台仅管理员可见，且必须持有未过期的管理员令牌
    const app = getApp();
    if (app.globalData.role !== "admin") {
      wx.switchTab({ url: "/pages/index/index" });
      return;
    }
    if (!app.globalData.adminToken) {
      wx.navigateTo({ url: "/pages/login/login" });
      return;
    }
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setData({ selected: 3, role: app.globalData.role });
    }
    this.loadOverview();
    this.loadEvents();
    this.loadBlacklist();
    this.loadQueue();
  },

  onPullDownRefresh() {
    Promise.all([this.loadOverview(), this.loadEvents(), this.loadBlacklist(), this.loadQueue()]).then(() =>
      wx.stopPullDownRefresh()
    );
  },

  loadOverview() {
    return api.get("/api/stats/overview").then((overview) => {
      const items = (overview.status && overview.status.items) || [];
      const exp = items.filter((x) => x.status === "EXPIRED");
      this.setData({ overview, expiredCount: exp.length ? exp[0].count : 0 });
    });
  },

  loadQueue() {
    return api.get("/api/queue").then((queue) => this.setData({ queue }));
  },

  goRefuse() {
    wx.navigateTo({ url: "/pages/refuse/refuse" });
  },

  goDashboard() {
    wx.navigateTo({ url: "/pages/dashboard/dashboard" });
  },

  // 超期闭环：ZSet 到期索引批量扫描 -> 批量退回快递公司
  sweepExpired() {
    this.setData({ sweeping: true });
    api
      .post("/api/parcels/expired/sweep", {})
      .then((r) => {
        wx.showToast({
          title: "扫描 " + r.checked + " 件，新增超期 " + r.expired + " 件",
          icon: "none",
          duration: 2500
        });
        this.loadOverview();
      })
      .finally(() => this.setData({ sweeping: false }));
  },

  returnExpired() {
    const n = this.data.expiredCount;
    if (!n) {
      wx.showToast({ title: "暂无超期未取包裹", icon: "none" });
      return;
    }
    wx.showModal({
      title: "超期件退回快递公司",
      content: "将把 " + n + " 件超期未取包裹退回，取件码立即失效，确定继续？",
      success: (res) => {
        if (!res.confirm) return;
        api.post("/api/parcels/expired/return", {}).then((r) => {
          wx.showToast({ title: "已退回 " + r.count + " 件", icon: "none" });
          this.loadOverview();
          this.loadEvents();
        });
      }
    });
  },

  setCurrent(p) {
    this.setData({
      current: p,
      currentTag: p ? TAG_MAP[p.status] || "tag-pending" : ""
    });
  },

  // 超期提醒：ZRANGEBYSCORE 扫描 + 事务管道批量迁移状态
  remindOverdue() {
    this.setData({ reminding: true });
    api
      .post("/api/remind/overdue", { hours: 48 })
      .then((res) => {
        wx.showToast({ title: "已生成 " + res.count + " 条超期提醒", icon: "none" });
        this.loadOverview();
        this.loadEvents();
      })
      .finally(() => this.setData({ reminding: false }));
  },

  onInput(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ ["form." + key]: e.detail.value });
  },

  onPick(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [key]: Number(e.detail.value) });
  },

  // 扫码入库：扫描快递面单单号，自动填入并识别快递公司
  scanTracking() {
    wx.scanCode({
      scanType: ["barCode", "qrCode"],
      success: (res) => {
        const code = (res.result || "").trim();
        if (!code) {
          wx.showToast({ title: "未识别到单号", icon: "none" });
          return;
        }
        const idx = this.guessCourier(code);
        this.setData({ "form.tracking_no": code, courierIndex: idx });
        wx.showToast({
          title: "已识别：" + COURIERS[idx] + " " + code.slice(-6),
          icon: "none"
        });
      },
      fail: () => wx.showToast({ title: "已取消扫码", icon: "none" })
    });
  },

  guessCourier(code) {
    const upper = code.toUpperCase();
    for (let i = 0; i < PREFIX_RULES.length; i++) {
      if (upper.indexOf(PREFIX_RULES[i][0]) === 0) {
        return COURIERS.indexOf(PREFIX_RULES[i][1]);
      }
    }
    return this.data.courierIndex;
  },

  onQueryInput(e) {
    this.setData({ queryKey: e.detail.value.trim() });
  },

  onAbnormalInput(e) {
    this.setData({ abnormalReason: e.detail.value });
  },

  onNewBlackInput(e) {
    this.setData({ newBlack: e.detail.value.trim() });
  },

  submitParcel() {
    const f = this.data.form;
    if (!f.receiver_id || !f.receiver || !f.tracking_no) {
      wx.showToast({ title: "收件人、账号、单号必填", icon: "none" });
      return;
    }
    const payload = {
      receiver_id: f.receiver_id,
      receiver: f.receiver,
      phone: f.phone,
      courier: COURIERS[this.data.courierIndex],
      category: CATEGORIES[this.data.categoryIndex],
      station: STATIONS[this.data.stationIndex],
      tracking_no: f.tracking_no,
      shelf: f.shelf,
      weight: Number(f.weight) || 0.5,
      ttl_days: Number(f.ttl_days) || 7
    };
    api.post("/api/parcels", payload).then((p) => {
      this.setData({ "form.tracking_no": "", "form.shelf": "" });
      this.setCurrent(p);
      wx.showToast({ title: "入库成功 " + p.id, icon: "none" });
      this.loadEvents();
    });
  },

  search() {
    const key = this.data.queryKey;
    if (!key) {
      wx.showToast({ title: "请输入包裹编号或快递单号", icon: "none" });
      return;
    }
    const byId = /^P\d+$/.test(key);
    const req = byId
      ? api.get("/api/parcels/" + key)
      : api.get("/api/parcels/tracking/" + key);
    req
      .then((res) => this.setCurrent(Array.isArray(res) ? res[0] : res))
      .catch(() => this.setCurrent(null));
  },

  markAbnormal() {
    if (!this.data.current) return;
    api
      .post("/api/parcels/" + this.data.current.id + "/abnormal", { reason: this.data.abnormalReason })
      .then((p) => {
        this.setCurrent(p);
        wx.showToast({ title: "已标记异常", icon: "none" });
      });
  },

  resetStatus() {
    if (!this.data.current) return;
    api
      .post("/api/parcels/" + this.data.current.id + "/status", { status: "PENDING", reason: "" })
      .then((p) => {
        this.setCurrent(p);
        this.loadOverview();
        wx.showToast({ title: "已恢复为待取件", icon: "none" });
      });
  },

  lightParcel() {
    if (!this.data.current) return;
    api.post("/api/parcels/" + this.data.current.id + "/light", {}).then((d) => {
      wx.showToast({ title: d.shelf + " 货架灯已点亮", icon: "none" });
    });
  },

  refuseParcel() {
    const cur = this.data.current;
    if (!cur) return;
    wx.showModal({
      title: "确认拒收",
      editable: true,
      placeholderText: "拒收原因（可选，拒收后取件码立即失效）",
      confirmText: "确认拒收",
      success: (res) => {
        if (!res.confirm) return;
        api
          .post("/api/parcels/" + cur.id + "/refuse", { reason: res.content || "" })
          .then((p) => {
            this.setCurrent(p);
            this.loadOverview();
            this.loadEvents();
            wx.showToast({ title: "已拒收", icon: "none" });
          });
      }
    });
  },

  returnParcel() {
    const cur = this.data.current;
    if (!cur) return;
    wx.showModal({
      title: "确认退货",
      editable: true,
      placeholderText: "退货原因（可选，确认后包裹交回驿站）",
      confirmText: "确认退货",
      success: (res) => {
        if (!res.confirm) return;
        api
          .post("/api/parcels/" + cur.id + "/return", { reason: res.content || "" })
          .then((p) => {
            this.setCurrent(p);
            this.loadOverview();
            this.loadEvents();
            wx.showToast({ title: "已退货", icon: "none" });
          });
      }
    });
  },

  generateCode() {
    if (!this.data.current) return;
    api.post("/api/parcels/" + this.data.current.id + "/code", {}).then((c) => {
      wx.showModal({
        title: "取件码已生成",
        content: "取件码：" + c.code + "\n有效期 " + (c.ttl / 86400) + " 天",
        showCancel: false
      });
    });
  },

  removeParcel() {
    if (!this.data.current) return;
    const id = this.data.current.id;
    wx.showModal({
      title: "确认删除",
      content: "将同时清理该包裹在 Redis 中的所有索引，确定删除 " + id + "？",
      success: (res) => {
        if (!res.confirm) return;
        api.del("/api/parcels/" + id).then(() => {
          this.setCurrent(null);
          wx.showToast({ title: "已删除", icon: "none" });
          this.loadEvents();
        });
      }
    });
  },

  loadEvents() {
    return api.get("/api/events?count=10").then((list) => {
      this.setData({
        events: list.map((x) => ({ ...x, timeText: x.time || "" }))
      });
    });
  },

  loadBlacklist() {
    return api.get("/api/blacklist").then((list) => this.setData({ blacklist: list }));
  },

  addBlack() {
    const uid = this.data.newBlack;
    if (!uid) return;
    api.post("/api/blacklist", { user_id: uid, reason: "人工加入" }).then(() => {
      this.setData({ newBlack: "" });
      this.loadBlacklist();
      wx.showToast({ title: "已加入黑名单", icon: "none" });
    });
  },

  removeBlack(e) {
    const uid = e.currentTarget.dataset.uid;
    api.del("/api/blacklist/" + uid).then(() => {
      this.loadBlacklist();
      wx.showToast({ title: "已移除", icon: "none" });
    });
  },

  callNext() {
    api.post("/api/queue/call", {}).then((r) => {
      const extra = r.shelf ? " · 灯亮 " + r.shelf : "";
      wx.showToast({ title: "叫号：" + r.serving + extra, icon: "none" });
      this.loadQueue();
      this.loadEvents();
    });
  }
});
