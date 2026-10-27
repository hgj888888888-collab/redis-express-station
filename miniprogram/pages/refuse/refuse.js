const api = require("../../utils/api");

const TABS = [
  { key: "REFUSED", label: "已拒收" },
  { key: "RETURNED", label: "已退货" }
];

Page({
  data: {
    tabs: TABS,
    tab: "REFUSED",
    keyword: "",
    list: [],
    total: 0,
    countRefused: 0,
    countReturned: 0,
    loading: false
  },

  onShow() {
    // 拒收 / 退货管理仅管理员可见
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
    return Promise.all([
      api.get("/api/parcels?status=REFUSED&limit=200"),
      api.get("/api/parcels?status=RETURNED&limit=200")
    ])
      .then(([refused, returned]) => {
        this._all = [
          ...refused.map((p) => this.decorate(p, "REFUSED")),
          ...returned.map((p) => this.decorate(p, "RETURNED"))
        ];
        this.setData({
          countRefused: refused.length,
          countReturned: returned.length,
          total: refused.length + returned.length,
          loading: false
        });
        this.applyFilter();
      })
      .catch(() => this.setData({ loading: false }));
  },

  decorate(p, key) {
    return {
      ...p,
      tagClass: key === "REFUSED" ? "tag-refused" : "tag-returned",
      reason: key === "REFUSED" ? p.refused_reason : p.return_reason,
      timeText: key === "REFUSED" ? p.refused_time_text : p.return_time_text
    };
  },

  switchTab(e) {
    this.setData({ tab: e.currentTarget.dataset.key });
    this.applyFilter();
  },

  onKeyword(e) {
    this.setData({ keyword: e.detail.value.trim().toLowerCase() });
    this.applyFilter();
  },

  applyFilter() {
    const kw = this.data.keyword;
    const list = (this._all || [])
      .filter((p) => p.status === this.data.tab)
      .filter(
        (p) =>
          !kw ||
          [p.id, p.tracking_no, p.receiver, p.receiver_id]
            .join(" ")
            .toLowerCase()
            .indexOf(kw) >= 0
      );
    this.setData({ list });
  },

  restore(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: "撤销拒收",
      content: "将 " + id + " 恢复为待取件，并重新生成取件码，取件码有效期 7 天。",
      success: (res) => {
        if (!res.confirm) return;
        api.post("/api/parcels/" + id + "/restore", {}).then(() => {
          wx.showToast({ title: "已恢复待取件", icon: "none" });
          this.load();
        });
      }
    });
  },

  // 拒收件发回发出地：已拒收 → 已退货，可填写退回原因
  sendBack(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: "发回发出地",
      editable: true,
      placeholderText: "退回原因（可选，默认：拒收，原路退回发出地）",
      confirmText: "确认发回",
      success: (res) => {
        if (!res.confirm) return;
        api.post("/api/parcels/" + id + "/origin", { reason: res.content || "" }).then(() => {
          wx.showToast({ title: "已发回发出地", icon: "none" });
          this.load();
        });
      }
    });
  },

  remove(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: "删除记录",
      content: "将彻底删除 " + id + " 及其在 Redis 中的所有索引，确定删除？",
      success: (res) => {
        if (!res.confirm) return;
        api.del("/api/parcels/" + id).then(() => {
          wx.showToast({ title: "已删除", icon: "none" });
          this.load();
        });
      }
    });
  }
});
