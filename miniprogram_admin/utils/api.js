// 后端接口地址：微信开发者工具中需勾选「不校验合法域名」
// 手机预览需改为电脑的局域网 IP（电脑与手机须在同一 Wi-Fi）
const BASE_URL = "http://172.17.176.42:5000";

// 请求头里自动带上管理员令牌：管理端接口需要，普通用户接口不校验
function authHeader() {
  const header = {};
  const app = typeof getApp === "function" ? getApp() : null;
  if (app && app.globalData && app.globalData.adminToken) {
    header["X-Admin-Token"] = app.globalData.adminToken;
  }
  return header;
}

function request(method, path, data) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method: method,
      data: data || {},
      header: Object.assign({ "content-type": "application/json" }, authHeader()),
      timeout: 8000,
      success(res) {
        if (res.data && res.data.ok) {
          resolve(res.data.data);
          return;
        }
        const msg = (res.data && res.data.message) || "请求失败";
        wx.showToast({ title: msg, icon: "none", duration: 2200 });
        reject(new Error(msg));
      },
      fail(err) {
        wx.showToast({
          title: "无法连接后端，请先运行 python app.py",
          icon: "none",
          duration: 2500
        });
        reject(err);
      }
    });
  });
}

function fmtTime(ts) {
  if (!ts) return "-";
  const d = new Date(Number(ts) * 1000);
  const p = (n) => (n < 10 ? "0" + n : "" + n);
  return (
    d.getFullYear() +
    "-" + p(d.getMonth() + 1) +
    "-" + p(d.getDate()) +
    " " + p(d.getHours()) +
    ":" + p(d.getMinutes())
  );
}

module.exports = {
  BASE_URL,
  get: (p) => request("GET", p),
  post: (p, d) => request("POST", p, d),
  del: (p, d) => request("DELETE", p, d),
  fmtTime
};
