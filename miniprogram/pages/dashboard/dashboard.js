const api = require("../../utils/api");

const STATUS_COLORS = {
  PENDING: "#1E4FD8",
  PICKED: "#12A150",
  EXPIRED: "#C7860A",
  ABNORMAL: "#D94A4A",
  REFUSED: "#8A93A6",
  RETURNED: "#2A7AB8"
};

Page({
  data: {
    daily: [],
    status: [],
    couriers: [],
    total: 0,
    uniqueUsers: 0,
    today: { inbound: 0, picked: 0 },
    loading: false
  },

  onShow() {
    if (getApp().globalData.role !== "admin") {
      wx.switchTab({ url: "/pages/index/index" });
      return;
    }
    this.load();
  },

  onPullDownRefresh() {
    this.load().then(() => wx.stopPullDownRefresh());
  },

  load() {
    this.setData({ loading: true });
    return api
      .get("/api/stats/dashboard")
      .then((d) => {
        const maxDaily = Math.max(1, ...d.daily.map((x) => x.inbound), ...d.daily.map((x) => x.picked));
        const daily = d.daily.map((x) => ({
          date: (x.date || "").slice(5),
          inbound: x.inbound,
          picked: x.picked,
          inboundH: Math.max(4, Math.round((x.inbound / maxDaily) * 180)),
          pickedH: Math.max(4, Math.round((x.picked / maxDaily) * 180))
        }));

        const maxStatus = Math.max(1, ...d.status.items.map((x) => x.count));
        const status = d.status.items.map((x) => ({
          ...x,
          color: STATUS_COLORS[x.status] || "#1E4FD8",
          width: Math.round((x.count / maxStatus) * 100)
        }));

        const maxCourier = Math.max(1, ...d.couriers.map((x) => x.count));
        const couriers = d.couriers.map((x) => ({
          ...x,
          width: Math.round((x.count / maxCourier) * 100)
        }));

        this.setData({
          daily,
          status,
          couriers,
          total: d.total,
          uniqueUsers: d.unique_pickup_users,
          today: d.today || { inbound: 0, picked: 0 },
          loading: false
        });
      })
      .catch(() => this.setData({ loading: false }));
  }
});
