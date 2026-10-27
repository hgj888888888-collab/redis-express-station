const api = require("../../utils/api");

const TAG_MAP = {
  PENDING: "tag-pending",
  PICKED: "tag-picked",
  ABNORMAL: "tag-abnormal",
  REFUSED: "tag-refused",
  RETURNED: "tag-returned",
  EXPIRED: "tag-expired"
};

Page({
  data: {
    id: "",
    parcel: null,
    code: "",
    ttl: 0,
    tagClass: "",
    inboundText: "",
    pickedText: "",
    lightOn: false,
    lightShelf: "",
    lightLeft: 0
  },

  onLoad(options) {
    this.setData({ id: options.id });
  },

  onShow() {
    this.load();
  },

  load() {
    api.get("/api/parcels/" + this.data.id).then((p) => {
      this.setData({
        parcel: p,
        tagClass: TAG_MAP[p.status] || "tag-pending",
        inboundText: api.fmtTime(p.inbound_time),
        pickedText: p.picked_time ? api.fmtTime(p.picked_time) : ""
      });
      if (p.status === "PENDING" || p.status === "EXPIRED") {
        api
          .get("/api/parcels/" + p.id + "/code")
          .then((c) => this.setData({ code: c.code, ttl: c.ttl }))
          .catch(() => this.setData({ code: "" }));
      }
    });
  },

  lightShelf() {
    api.post("/api/parcels/" + this.data.id + "/light", {}).then((d) => {
      this.setData({
        lightOn: true,
        lightShelf: d.shelf,
        lightLeft: d.ttl
      });
      clearInterval(this._lightTimer);
      this._lightTimer = setInterval(() => {
        const left = this.data.lightLeft - 1;
        if (left <= 0) {
          clearInterval(this._lightTimer);
          this.setData({ lightOn: false, lightLeft: 0 });
        } else {
          this.setData({ lightLeft: left });
        }
      }, 1000);
      wx.showToast({ title: "货架灯已点亮", icon: "success" });
    });
  },

  refuse() {
    wx.showModal({
      title: "拒收包裹",
      editable: true,
      placeholderText: "拒收原因（可选，拒收后取件码立即失效）",
      confirmText: "确认拒收",
      success: (res) => {
        if (!res.confirm) return;
        api
          .post("/api/parcels/" + this.data.id + "/refuse", { reason: res.content || "" })
          .then(() => {
            wx.showToast({ title: "已拒收", icon: "none" });
            this.load();
          });
      }
    });
  },

  applyReturn() {
    wx.showModal({
      title: "申请退货",
      editable: true,
      placeholderText: "退货原因（可选，确认后请将商品交回驿站）",
      confirmText: "提交退货",
      success: (res) => {
        if (!res.confirm) return;
        api
          .post("/api/parcels/" + this.data.id + "/return", { reason: res.content || "" })
          .then(() => {
            wx.showToast({ title: "退货已提交", icon: "none" });
            this.load();
          });
      }
    });
  },

  onUnload() {
    clearInterval(this._lightTimer);
  },

  generateCode() {
    api.post("/api/parcels/" + this.data.id + "/code", {}).then((c) => {
      this.setData({ code: c.code, ttl: c.ttl });
      wx.showToast({ title: "取件码已更新", icon: "none" });
    });
  },

  copyCode() {
    wx.setClipboardData({ data: this.data.code });
  },

  goPickup() {
    wx.switchTab({ url: "/pages/pickup/pickup" });
  }
});
