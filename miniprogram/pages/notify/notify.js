const api = require("../../utils/api");

Page({
  data: {
    userId: "",
    items: [],
    unread: 0,
    loading: false
  },

  onShow() {
    const uid = getApp().globalData.userId;
    this.setData({ userId: uid });
    if (!uid) return;
    this.load(uid);
  },

  onPullDownRefresh() {
    this.load(this.data.userId).then(() => wx.stopPullDownRefresh());
  },

  load(uid) {
    this.setData({ loading: true });
    return api
      .get("/api/users/" + uid + "/notifications?limit=50")
      .then((d) => {
        this.setData({
          items: d.items.map((x, i) => ({ ...x, key: i })),
          unread: d.unread,
          loading: false
        });
        if (d.unread > 0) {
          api.post("/api/users/" + uid + "/notifications/read", {}).catch(() => {});
        }
      })
      .catch(() => this.setData({ loading: false }));
  },

  goParcel() {
    wx.switchTab({ url: "/pages/index/index" });
  }
});
