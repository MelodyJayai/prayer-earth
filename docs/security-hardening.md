# 网站安全加固与故障响应

## 已上线的基础防护

- 源站只监听 `127.0.0.1:18080`，公网只通过 Cloudflare Tunnel 进入。
- 静态服务使用专用 `prayer-web` 用户运行；Cloudflare Tunnel 使用专用 `cloudflared` 用户运行。
- systemd 已启用 `NoNewPrivileges`、`ProtectSystem=strict`、`PrivateTmp`、资源上限和地址族限制。
- 网站文件由 root 管理，内容数据库和图片目录单独由 `prayer-web` 管理。
- 管理写接口按客户端地址限制突发写操作；登录接口仍有账号/IP 失败限制。
- 上传继续执行格式、尺寸、像素、数量和总大小限制，并重新编码去除元数据。
- 管理 Cookie 使用 `HttpOnly`、`Secure`、`SameSite=Strict`；写操作需要 CSRF 和同源校验。
- 全站增加 HSTS、CSP、`X-Frame-Options`、`nosniff`、`Permissions-Policy` 和 CORP 响应头。
- 不存在的扫描路径和点文件路径返回 404，不再统一回退到首页。
- `/api/content` 使用内容版本 ETag 和短时间缓存，减少重复全量序列化。
- 每 15 分钟生成一次 SQLite 一致性备份，保留最近 14 份。
- 每 15 分钟生成一次不含数据库和管理接口的静态阅读快照，保存在服务器的 `snapshots/current`。
- `reader.bytelanework.com` 发布为完整的 Workers Static Assets 只读镜像；发布电脑仅上传已发布快照，备用站无回源、无管理入口、无写接口。
- `diagport.com` 边缘已启用 Always Use HTTPS 和最低 TLS 1.2；备用域名也强制 HTTPS。

## 日常检查

```sh
sudo systemctl is-active prayer-earth-trial.service prayer-earth-trial-tunnel.service
sudo systemctl is-active prayer-earth-trial-backup.timer prayer-earth-trial-snapshot.timer
sudo systemctl status prayer-earth-trial-backup.service prayer-earth-trial-snapshot.service
sudo journalctl -u prayer-earth-trial.service -n 100 --no-pager
sudo journalctl -u prayer-earth-trial-tunnel.service -n 100 --no-pager
```

公网检查至少包括：主站首页、`/reader/index.html`、`/api/content`、一张图片和一个不存在的路径。200 状态还要核对页面正文和内容版本，不能只看 HTTP 状态码。

## 攻击或异常时的处理顺序

1. 先确认只读阅读页面是否正常；必要时暂时停用 `/admin` 和 `/api/admin/*` 的公网访问，保留只读阅读。
2. 在 Cloudflare 控制台临时提高安全级别，并为登录、管理接口和上传接口启用边缘限速/WAF 规则。
3. 如果怀疑管理员凭据泄露，立即停用相关账号、撤销会话、重置密码，并检查审计记录。
4. 如果怀疑主机或 Tunnel 凭据泄露，停止写入，轮换 Tunnel token、Cloudflare API token 和部署 SSH 密钥。
5. 从已知干净版本和最近一致性备份恢复，先校验文件哈希和内容数量，再原子切换。
6. 恢复后检查服务用户、systemd 硬化状态、磁盘空间、日志增长和最近的 401/403/429/5xx。
7. 将事件时间、受影响入口、最后一个正常内容版本和恢复动作记录下来。

备用站的发布凭据只在发布电脑保存。若发布电脑被怀疑入侵，先停用 `Prayer-Reader-Snapshot-Publish`，撤销并重建 Cloudflare API token，再从已知干净目录重新发布；主站的 Tunnel token 和管理员密码不因此自动暴露。

备用站已使用不同域名和不同 Cloudflare 账户，完整页面与图片由静态资产托管，可隔离主站的 OCI 和 Tunnel 故障。两个站仍共享 Cloudflare，不能保证地区线路或供应商级故障时均可用；第二家供应商尚待接入。镜像运维见 `docs/reader-failover.md`。

Cloudflare 边缘 WAF/管理接口限速规则尚未通过本项目的现有 token 配置，不能视为已经启用；目前由应用层限制登录失败、管理写入和上传负载。需要拥有该区域安全规则权限的管理员在控制台补齐边缘规则。数据库备份目前保留在源站，公开静态镜像不能替代数据库的异地私有备份。
