const api = require("../../utils/api");

Page({
  data: {
    status: null,
    rankUsers: [],
    rankStay: [],
    overdue: [],
    overdueHours: 48,
    today: null,
    uniqueUsers: 0,
    maxUserCount: 1,
    maxStay: 1
  },

  onShow() {
    // 排行榜仅管理员可见
    if (getApp().globalData.role !== "admin") {
      wx.switchTab({ url: "/pages/index/index" });
      return;
    }
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setData({ selected: 2, role: getApp().globalData.role });
    }
    this.load();
  },

  onPullDownRefresh() {
    this.load().then(() => wx.stopPullDownRefresh());
  },

  load() {
    return Promise.all([
      api.get("/api/stats/status"),
      api.get("/api/stats/rank/users?top=5"),
      api.get("/api/stats/rank/stay?top=5"),
      api.get("/api/stats/daily"),
      api.get("/api/stats/pickup-users")
    ]).then(([status, ru, rs, today, pu]) => {
      this.setData({
        status: status,
        rankUsers: ru,
        rankStay: rs,
        today: today,
        uniqueUsers: pu.unique_users,
        maxUserCount: ru.length ? ru[0].parcel_count : 1,
        maxStay: rs.length ? rs[0].stay_hours : 1
      });
    });
  },

  scanOverdue(e) {
    const hours = Number(e.currentTarget.dataset.hours);
    this.setData({ overdueHours: hours });
    api.get("/api/stats/overdue?hours=" + hours).then((list) => {
      this.setData({ overdue: list });
      wx.showToast({
        title: list.length ? "发现 " + list.length + " 件滞留包裹" : "暂无滞留包裹",
        icon: "none"
      });
    });
  },

  remind() {
    api.post("/api/remind/overdue", { hours: this.data.overdueHours }).then((r) => {
      wx.showToast({ title: "已生成 " + r.count + " 条提醒", icon: "none" });
      this.load();
    });
  }
});
