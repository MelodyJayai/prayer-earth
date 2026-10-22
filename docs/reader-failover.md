# 备用阅读站运维说明

## 地址与范围

- 主站：<https://prayer.diagport.com>
- 备用只读站：<https://reader.bytelanework.com>
- 备用站只发布已发布的 HTML、图片、`manifest.json` 和 `health.json`；没有数据库、管理员入口、登录会话、草稿或写接口。
- 备用站由 `prayer-reader-failover` Workers Static Assets 提供，固定绑定 `reader.bytelanework.com`；`workers.dev` 预览入口已关闭。

## 自动更新

Windows 任务 `Prayer-Reader-Snapshot-Publish` 使用 S4U、每 15 分钟运行一次。任务先让源站生成一致性快照，再通过固定 SSH 主机指纹拉取公开文件，核对路径、哈希、引用和图片，最后一次性发布到静态 Worker。任何拉取、校验或上传失败都会保留上一次完整版本。

发布状态和日志只保存在本机：

```powershell
Get-ScheduledTask -TaskName Prayer-Reader-Snapshot-Publish
Get-ScheduledTaskInfo -TaskName Prayer-Reader-Snapshot-Publish
Get-Content .reader-publish\publisher.log -Tail 30
```

手工补跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-reader-publisher.ps1
```

不要把 `D:\Fight\OracleFree\ops\.cf-token-proxy` 复制到服务器、仓库或聊天中。备用站发布凭据仅由发布电脑使用。

## 验收检查

```powershell
python scripts\deploy-reader-failover.py --snapshot-directory .reader-publish\snapshot --verify-only --full-verify
```

远程检查应返回：根地址 302 到 `/reader/index.html` 后为 200；两个栏目、任一详情页和任一图片为 200；`/admin`、`/api/content` 和未知详情页为 404；POST 为 405。`health.json` 中的内容版本、晨修数量和宣教数量应与主站快照一致。

备用站和主站均在 Cloudflare，但属于不同账户；这能隔离 OCI、源站服务和 Tunnel 故障，不能保证 Cloudflare 或某条地区线路发生整体故障时仍可用。正式上线前仍应增加第二家静态托管商。
