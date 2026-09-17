# 发布到 GitHub Pages

云端每天北京时间约 **09:35、17:35** 抓取并发布；GitHub 排队可能延迟。2026-09-17 已调整到白天，避开近期凌晨连续连接超时的时段。本机 02:15 任务只更新本地文件，与云端任务独立。

主抓取在 Linux 执行，失败时使用独立 Windows 执行器再试一次，两者都强制 IPv4。发布只使用本次成功抓取的页面；抓取产物不含 Cookie、数据库或原始小红书资料。

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

学校站点可能发生连接超时。两路都失败时：定时/手动更新明确报错、不覆盖线上页面；代码推送允许发布已保存快照，但显示刷新失败提示并保留原抓取时间，绝不把缓存标成刚抓取。不能通过关闭失败通知假装问题已解决。

`Diagnose school connectivity (no deployment)` 可手动检查 Linux/Windows 的 DNS、TCP、TLS 及两个公开接口，不会部署。`Update and publish job radar` 的 `test_fallback` 选项跳过主抓取，用真实学校数据验证 Windows 备用路线；日常无需勾选。

2026-09-17 对照测试：两种执行器白天 IPv4 的 TCP/TLS/API 均成功，Linux IPv6 为 Network is unreachable。凌晨超时是否由校方维护或线路策略引起，现有证据无法确定；白天调度与备用路线提升容错，但无法保证学校站点永远可达。
