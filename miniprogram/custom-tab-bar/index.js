const LIST = [
  { pagePath: "/pages/index/index", text: "首页", index: 0, adminOnly: false },
  { pagePath: "/pages/pickup/pickup", text: "取件", index: 1, adminOnly: false },
  { pagePath: "/pages/stats/stats", text: "排行", index: 2, adminOnly: true },
  { pagePath: "/pages/admin/admin", text: "管理", index: 3, adminOnly: true }
];

Component({
  data: {
    role: "user",
    selected: 0,
    list: LIST
  },

  lifetimes: {
    attached() {
      this.refreshRole();
    }
  },

  pageLifetimes: {
    show() {
      this.refreshRole();
    }
  },

  methods: {
    // 普通用户只看到首页与取件，管理员额外看到排行与管理
    refreshRole() {
      const app = getApp();
      const role = (app.globalData && app.globalData.role) || "user";
      if (role !== this.data.role) {
        this.setData({ role });
      }
    },

    switchTab(e) {
      const url = e.currentTarget.dataset.url;
      if (!url) return;
      wx.switchTab({
        url: url,
        fail: () => wx.reLaunch({ url: url })
      });
    }
  }
});
