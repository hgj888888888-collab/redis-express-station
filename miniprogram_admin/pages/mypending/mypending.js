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
    parcels: [],
    loading: false
  },

  onShow() {
    const app = getApp();
    this.setData({ userId: app.globalData.userId });
    this.load();
  },

  onPullDownRefresh() {
    this.load().then(() => wx.stopPullDownRefresh());
  },

  load() {
    const uid = this.data.userId;
    if (!uid) return Promise.resolve();
    this.setData({ loading: true });
    return api
      .get("/api/users/" + uid + "/parcels")
      .then((list) => {
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
          parcels: pending,
          userName: list.length ? list[0].receiver : "",
          loading: false
        });
      })
      .catch(() => this.setData({ loading: false }));
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: "/pages/detail/detail?id=" + id });
  }
});
