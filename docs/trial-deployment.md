# 同工试用网页部署记录

## 当前入口

- 网址：https://prayer.diagport.com
- 服务器：OCI `a1-main`，站点目录 `/opt/prayer-earth-trial/site`
- 网页服务：`prayer-earth-trial.service`，仅监听 `127.0.0.1:18080`
- 独立隧道：`prayer-earth-trial-tunnel.service`，Cloudflare Named Tunnel `prayer-earth-trial`
- 隧道令牌：`/etc/prayer-earth-trial/tunnel-token.txt`，`cloudflared:cloudflared`、权限 600；不写入客户端或文档
- 静态服务用户：`prayer-web`；站点文件 root 只读，内容数据和备份目录独立可写
- 自动任务：`prayer-earth-trial-backup.timer`（15 分钟备份）和 `prayer-earth-trial-snapshot.timer`（15 分钟生成只读快照）

备用阅读入口：`https://prayer.diagport.com/reader/index.html`。该入口是部署产物中的纯 HTML 页面，主应用脚本加载失败时仍可浏览导入内容。Cloudflare Tunnel 固定使用 HTTP/2，避免 OCI 到 Cloudflare 的 QUIC 区域预检差异。

完整静态备用站：`https://reader.bytelanework.com`，独立于 OCI 源站和 Tunnel，由不同 Cloudflare 账户的 Workers Static Assets 保存全部已发布页面与图片。运维电脑的 `Prayer-Reader-Snapshot-Publish` 任务每 15 分钟同步；2026-10-19 首次任务返回 0，已完成全量页面和图片哈希验证。发布日志、失败处理与边界见 `docs/reader-failover.md`。

## 2026-10-18 Error 1033 修复

同工截图显示 Cloudflare Error 1033。排查确认网页和隧道两个服务均为 `disabled`、`inactive`，Cloudflare 报隧道 `inactive`、连接数 0。此前部署的最后一步 SSH 启动命令未成功完成，上传文件不等于站点已就绪。

已启用并启动两个服务，设置开机自启、失败自动重启。隧道令牌改用受限权限的令牌文件，避免出现在进程命令行。修复后 Cloudflare 隧道为 `healthy`、4 条连接，首页、内容库、详情深链接、图片 GET 均返回 200；浏览器已能加载内容及图片。

部署脚本原先需要多次新建 SSH 连接，而服务器配置了 SSH 新连接频率限制。后续部署应通过单个 SSH 会话安装和启动，并在服务和网页校验成功后确认发布完成；修复时无需重新上传整个图片集。

## 日常检查

SSH 登录后执行以下命令即可检查本项目，不涉及现有其他业务：

```bash
systemctl is-enabled prayer-earth-trial.service prayer-earth-trial-tunnel.service
systemctl is-active prayer-earth-trial.service prayer-earth-trial-tunnel.service
systemctl is-active prayer-earth-trial-backup.timer prayer-earth-trial-snapshot.timer
curl --fail --max-time 15 http://127.0.0.1:18080/ -o /dev/null
```

两项服务均应为 `enabled`、`active`。外网同时检查首页及一条内容深链接；仅检查域名 DNS 或服务器端口不能证明网页可用。

如两个服务未启动：

```bash
sudo systemctl enable --now prayer-earth-trial.service prayer-earth-trial-tunnel.service prayer-earth-trial-backup.timer prayer-earth-trial-snapshot.timer
```

服务已在运行但仍报错时，先检查对应服务日志及 Cloudflare 的连接状态，避免盲目重新发布 DNS 或覆盖已有业务配置。
