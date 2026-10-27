App({
  globalData: {
    // 演示用：默认为演示数据中的高包裹量用户，可在首页切换
    userId: "20211003",
    // user：普通用户（首页 / 取件）；admin：管理员（额外开放排行 / 管理）
    role: "user",
    adminName: "",
    // 管理端访问令牌：管理员登录后由后端签发，随请求头一起发送
    adminToken: ""
  },

  onLaunch() {
    const saved = wx.getStorageSync("userId");
    if (saved) {
      this.globalData.userId = saved;
    }
    const role = wx.getStorageSync("role");
    if (role) {
      this.globalData.role = role;
      this.globalData.adminName = wx.getStorageSync("adminName") || "";
      this.globalData.adminToken = wx.getStorageSync("admin_token") || "";
    }
  },

  setUserId(uid) {
    this.globalData.userId = uid;
    wx.setStorageSync("userId", uid);
  },

  setAdminToken(token) {
    this.globalData.adminToken = token || "";
    wx.setStorageSync("admin_token", this.globalData.adminToken);
  },

  setRole(role, name) {
    this.globalData.role = role;
    this.globalData.adminName = name || "";
    wx.setStorageSync("role", role);
    wx.setStorageSync("adminName", name || "");
  },

  clearRole() {
    this.setRole("user", "");
    this.setAdminToken("");
  }
});
