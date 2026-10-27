const api = require("../../utils/api");

Page({
  data: {
    username: "",
    password: "",
    submitting: false
  },

  onUsernameInput(e) {
    this.setData({ username: e.detail.value });
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value });
  },

  submit() {
    const { username, password } = this.data;
    if (!username || !password) {
      wx.showToast({ title: "请输入账号和密码", icon: "none" });
      return;
    }
    this.setData({ submitting: true });
    api
      .post("/api/auth/login", { username, password })
      .then((res) => {
        getApp().setAdminToken(res.token);
        getApp().setRole("admin", res.name);
        wx.showToast({ title: "登录成功", icon: "none" });
        setTimeout(() => wx.switchTab({ url: "/pages/admin/admin" }), 500);
      })
      .finally(() => this.setData({ submitting: false }));
  }
});
