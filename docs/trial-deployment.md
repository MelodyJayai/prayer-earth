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

## Expo Router 直链（SPA 白名单回退）

`npm run build:web` 的 `dist` 只有一份应用入口 `index.html`。Expo Router 的这些页面在磁盘上没有对应文件，所以以前直接打开 `https://prayer.diagport.com/prayers` 会 404。`scripts/serve-static.py` 现在只在 GET 和 HEAD、并且站点目录里没有同名文件时，把下面这些路径改写成 `index.html`，状态码仍是 200。浏览器地址栏不变，由前端路由接着打开对应页面。

- `/prayers`、`/testimonies`、`/profile`、`/about`、`/compose`
- `/legal/community`、`/legal/privacy`
- `/content/<id>`、`/prayer/<id>`：`id` 只有一层，首字符为字母或数字，其余只能是字母、数字、下划线和连字符，最长 81 个字符

路径末尾多一个 `/` 同样算命中。查询字符串不参与判断。若该路径本身是已存在的文件，或是带 `index.html` 的目录，仍返回那个真实文件，不改写成入口。

这不是全站回退。下面的请求保持原来的结果：

- `/api/*`，包括 `/api/content` 和不存在的 `/api/...`
- `/admin` 以及管理接口
- `/reader` 与 `/reader/*`（未知阅读页仍是 404）
- 不存在的静态资源，以及任何不在白名单里的路径
- 点文件，以及原始或百分号编码后含 `/.`、`..` 的路径（避免被静态处理器折回站点根目录）
- POST、PUT、PATCH（祷告页面的这些方法仍是 404，不会返回入口 HTML）

安全响应头、HTML 的 `Cache-Control: no-cache`、带内容哈希的静态文件长期缓存，都按改写之后实际发送的文件计算，规则本身没有放宽。

部署脚本仍会把远端 `/opt/prayer-earth-trial/site` 整目录换成新的 `dist`，并删掉刚换下的 `site.previous`。上线前先把当前 `site` 另存备份，再把旧目录里有、新包里没有的图片并进新目录，然后才切换。内容数据库在 `data/`，不在这次被替换的 `site` 里。

这次上线会在打开数据库时给 `news` 表补上 `needs_prayer` 和 `prayer_excluded`（默认 0）。切换前先备份 `/opt/prayer-earth-trial/data`，至少复制 `admin.sqlite3` 及其 WAL。迁移不删行；若要回滚代码，先停服务，用这份备份换回数据库，再换回上一版 `site`。不要在未备份时删掉新列。

祷告页是 `GET /api/prayer-requests`（同源，只读）。已分流的动态不在 `GET /api/content` 里重复出现。两边的 `version` 相同；分流变化时这个版本加 1，备用站快照会连同 `reader/prayers.html` 一起变，签名随之变化。备用站仍不提供 `/api/content` 或 `/api/prayer-requests`。

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
