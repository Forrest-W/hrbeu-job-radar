# 发布到 GitHub Pages

这个项目已经配置好自动任务：每天北京时间约 02:15，GitHub Actions 会抓取学校公开活动、重新生成 `index.html`，然后发布为网站。GitHub 的定时任务在高峰期可能晚一些执行。

## 第一次发布

1. 在 GitHub 新建一个仓库，建议命名为 `hrbeu-job-radar`。
2. 将本文件夹作为该仓库根目录上传（不要把它再套一层目录）。
3. 打开仓库 **Settings → Pages**，在 **Build and deployment** 中选择 **GitHub Actions**。
4. 打开 **Actions → Update and publish job radar → Run workflow**，点击 **Run workflow**。
5. 等待约 1–3 分钟；成功后会在 Actions 运行详情的 `deploy` 步骤和 Settings → Pages 中显示网址。手机收藏这个网址即可。

## 可见性

GitHub Free 的 Pages 适合公开仓库。页面本身只有公开招聘活动与浏览器本地保存的筛选偏好；如果不想公开代码或页面，请不要启用 Pages，改用带访问控制的部署服务。

## 手动刷新

在 GitHub 的 Actions 页面点击 **Run workflow** 即可立即刷新；电脑上仍可双击 `refresh.bat` 生成本地版本。

## 发生失败时

学校站点偶尔会有网络握手超时。工作流会在日志中显示失败位置；重新运行一次通常即可。发布前只抓公开列表，不尝试绕过登录或访问个人数据。

GitHub hosted runner 对学校站点的 IPv6 路由可能不可用；工作流已强制使用 IPv4 访问，不需要额外配置。
