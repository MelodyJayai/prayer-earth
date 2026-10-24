# 备用阅读站运维说明

## 地址与范围

- 主站：<https://prayer.diagport.com>
- 备用只读站：<https://reader.bytelanework.com>
- 备用站只发布已发布的 HTML、图片、`manifest.json` 和 `health.json`；没有数据库、管理员入口、登录会话、草稿或写接口。
- 备用站由 `prayer-reader-failover` Workers Static Assets 提供，固定绑定 `reader.bytelanework.com`；`workers.dev` 预览入口已关闭。

## 自动更新

Windows 任务 `Prayer-Reader-Snapshot-Publish` 使用 S4U、每 15 分钟运行一次。任务先让源站生成一致性快照，再通过固定 SSH 主机指纹拉取公开文件，核对路径、哈希、引用和图片，最后一次性发布到静态 Worker。任何拉取、校验或上传失败都会保留上一次完整版本。

内容签名与上次成功发布相同时，发布机会核对公网快照并跳过 Cloudflare 部署。这条成功路径仍会把本机 `.reader-publish/state.json` 的 `verifiedAt` 更新为本次核对时间，并保留 `signature`、`contentVersion`、`counts`、`deploymentId`、`hostname` 以及其他已有字段。签名不一致时的 `--verify-only` 只做检查，不会把尚未发布的签名写进 `state.json`。

发布状态和日志只保存在本机：

```powershell
Get-ScheduledTask -TaskName Prayer-Reader-Snapshot-Publish
Get-ScheduledTaskInfo -TaskName Prayer-Reader-Snapshot-Publish
Get-Content .reader-publish\state.json
Get-Content .reader-publish\publisher.log -Tail 30
```

手工补跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-reader-publisher.ps1
```

不要把 `D:\Fight\OracleFree\ops\.cf-token-proxy` 复制到服务器、仓库或聊天中。备用站发布凭据仅由发布电脑使用。

## 怎样判断发布管道是否健康

公网 `https://reader.bytelanework.com/health.json` 的 `generatedAt` 是**烤进该份快照的上次内容发布时间**（生成那份已部署快照时写入的时间），不是发布管道的心跳。源站快照服务每次重做快照都会给本地 `health.json` 写上新的 `generatedAt`，即使内容文件没变。发布签名只覆盖内容文件哈希、内容版本、Worker 脚本和静态资源配置，不包含 `health.json`。因此内容未变时，公网 `generatedAt` 会停在上一次真正部署的时间，而本地快照会更新。这是预期行为。

不要把“公网 `generatedAt` 变旧”或“公网与源站 `generatedAt` 不一致”单独当成管道故障。例如内容版本仍是 2、条目数仍是 211，而公网 `generatedAt` 停留在几天前，同时日志写着 `public snapshot verified; no deployment needed`，说明发布机刚核对过、并且正确地没有重新部署。

同时满足下面三项才算健康：

1. **内容一致。** 公网 `health.json` 的 `contentVersion` 和 `counts` 与主站当前快照一致。主站快照看源站 `/opt/prayer-earth-trial/snapshots/current/health.json`（或同目录的 `manifest.json`）。只比较这两个字段，不要要求 `generatedAt` 相同。
2. **发布机仍在核对。** 计划任务 `Prayer-Reader-Snapshot-Publish` 最近一次运行结果为成功（`LastTaskResult` 为 0），并且本机 `.reader-publish/state.json` 的 `verifiedAt` 在大约两个任务间隔内仍是新的。任务每 15 分钟一次，也就是大约 30 分钟内。跳过部署的成功路径也会刷新 `verifiedAt`。
3. **日志可以合法地跳过部署。** 计划任务日志出现 `public snapshot verified; no deployment needed` 表示公网内容已核对，且内容签名与上次发布相同，所以没有重新部署。签名一致时，前面还会有一行 `publisher state verifiedAt refreshed`。手工 `--verify-only` 在签名不一致时也会打印前一句，但不会刷新 `verifiedAt`，也不会把新签名写入 `state.json`。

`generatedAt` 只有在内容签名变化并完成一次 Cloudflare 部署之后才会在公网上前进。它前进表示上次把内容发布进快照并部署出去的时间，不表示计划任务刚刚跑过。

### 为什么签名未变时不为了推进公网 health 而重新部署

发布任务每次拉取前都会启动源站快照服务，生成器即使用户内容没变也会把 `generatedAt` 写成当前时间。若“本地 `generatedAt` 新于公网”就部署，每 15 分钟都会新建一次 Workers 静态资源上传和 Worker 部署，而不是一次轻量心跳。公网 `generatedAt` 继续表示上次内容发布；发布机是否活着，看计划任务结果和本机 `verifiedAt`。

## 验收检查

```powershell
python scripts\deploy-reader-failover.py --snapshot-directory .reader-publish\snapshot --verify-only --full-verify
```

远程检查应返回：根地址 302 到 `/reader/index.html` 后为 200；两个栏目、任一详情页和任一图片为 200；`/admin`、`/api/content` 和未知详情页为 404；POST 为 405。`health.json` 中的内容版本、晨修数量和宣教数量应与主站快照一致。`generatedAt` 可以旧于源站当前快照，见上一节。签名与 `state.json` 一致时，这条手工核对也会刷新 `verifiedAt`。

备用站和主站均在 Cloudflare，但属于不同账户；这能隔离 OCI、源站服务和 Tunnel 故障，不能保证 Cloudflare 或某条地区线路发生整体故障时仍可用。正式上线前仍应增加第二家静态托管商。
