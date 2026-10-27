const api = require("../../utils/api");

const TAG_MAP = {
  PENDING: "tag-pending",
  PICKED: "tag-picked",
  ABNORMAL: "tag-abnormal",
  EXPIRED: "tag-expired"
};

Page({
  data: {
    userId: "",
    userName: "",
    role: "user",
    adminName: "",
    previewParcels: [],
    pendingCount: 0,
    unread: 0,
    loading: false
  },

  onShow() {
    const app = getApp();
    this.setData({
      userId: app.globalData.userId,
      role: app.globalData.role,
      adminName: app.globalData.adminName
    });
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0, role: app.globalData.role });
    }
    this.loadAll();
    this.loadUnread();
  },

  onPullDownRefresh() {
    this.loadAll().then(() => wx.stopPullDownRefresh());
  },

  loadAll() {
    const uid = this.data.userId;
    if (!uid) return Promise.resolve();
    this.setData({ loading: true });
    return api
      .get("/api/users/" + uid + "/parcels")
      .then((list) => {
        // 首页只展示未取件（待取 + 超期未取 + 异常待处理）
        const pending = list
          .filter(
            (p) => p.status === "PENDING" || p.status === "EXPIRED" || p.status === "ABNORMAL"
          )
          .map((p) => ({
            ...p,
            tagClass: TAG_MAP[p.status] || "tag-pending",
            inboundText: api.fmtTime(p.inbound_time)
          }));
        this.setData({
          previewParcels: pending.slice(0, 2),
          pendingCount: pending.length,
          userName: list.length ? list[0].receiver : "",
          loading: false
        });
      })
      .catch(() => this.setData({ loading: false }));
  },

  onUserIdInput(e) {
    this.setData({ userId: e.detail.value });
  },

  loadUnread() {
    const uid = this.data.userId;
    if (!uid) return Promise.resolve();
    return api
      .get("/api/users/" + uid + "/notifications?limit=1")
      .then((d) => this.setData({ unread: d.unread }))
      .catch(() => {});
  },

  // 切换用户：保存学号后直接按该学号刷新包裹列表
  switchUser() {
    const uid = (this.data.userId || "").trim();
    if (!uid) {
      wx.showToast({ title: "请输入学号/账号", icon: "none" });
      return;
    }
    getApp().setUserId(uid);
    this.setData({ userId: uid, userName: "" });
    this.loadAll();
    this.loadUnread();
    wx.showToast({ title: "已切换到 " + uid, icon: "none" });
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: "/pages/detail/detail?id=" + id });
  },

  goPickup() {
    wx.switchTab({ url: "/pages/pickup/pickup" });
  },

  goPending() {
    wx.navigateTo({ url: "/pages/mypending/mypending" });
  },

  goNotify() {
    wx.navigateTo({ url: "/pages/notify/notify" });
  },

  goLogin() {
    wx.navigateTo({ url: "/pages/login/login" });
  },

  logout() {
    wx.showModal({
      title: "退出管理员",
      content: "退出后仅保留首页与取件功能",
      success: (res) => {
        if (!res.confirm) return;
        getApp().clearRole();
        this.setData({ role: "user", adminName: "" });
        this.getTabBar && this.getTabBar().setData({ role: "user" });
        wx.showToast({ title: "已退出", icon: "none" });
      }
    });
  }
});
