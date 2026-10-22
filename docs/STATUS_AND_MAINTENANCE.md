# 祷告地球现状与维护建议

> 评估日期：2026-10-22  
> 评估对象：公开仓库 [`MelodyJayai/prayer-earth`](https://github.com/MelodyJayai/prayer-earth) 的 `main`，提交 `a410f28`（2026-10-22，说明为 “Initial import of Prayer Earth web trial and failover reader”）。  
> 对照材料：`README.md`、`ROADMAP_UPGRADE.md`（文档自标核对日 2026-09-05）、`docs/`、`package.json`、`app.json`、`eas.json`、`.env.example`、`.github/workflows/ci.yml`，以及 `app/`、`src/`、`scripts/`。  
> 公网抽查（只读，未登录管理后台、未 SSH）：`https://prayer.diagport.com/api/content`、`https://reader.bytelanework.com/health.json`。  
> 本文不修改功能代码。路线图第 2 节有多处已被后续代码推翻，维护决策以本文和 `docs/trial-status.md`（2026-10-19）为准。

## 一句话结论

现在能维护的是一套**同工向的网页内容阅读站**（晨修 / 宣教图片、受保护的发布后台、静态备用阅读站），外加一个**默认离线的祷告客户端壳**；它还不是路线图里的全球祷告社区。下一步应先选定这条产品线，而不是同时开工 Phase 2–4。

## 现状要点

### 仓库与版本

- 应用版本在 `package.json` 与 `app.json` 中都是 `1.1.0`。技术栈与 README 一致：Expo `~57.0.31`、React Native `0.86.3`、React `19.2.3`、Expo Router、TypeScript `strict`。
- iOS `buildNumber` 与 Android `versionCode` 均为 `2`。Bundle ID / Package Name 仍是 `org.prayerearth.app`。`app.json` 没有 `extra.eas.projectId`。`eas.json` 只有 development / preview / production 构建档，`submit.production` 为空对象。
- 公开仓库创建于 2026-10-22，默认分支 `main`，无 license，无 tag，无其他分支。GitHub issue 与 pull request 均为空。可追溯历史只有上述一次导入提交，更早的开发过程不在这个远程仓库里。
- CI 只有 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)：向 `main` / `master` 推送或打开 PR 时，在 Node.js 24 与 Python 3.14 上执行 typecheck、ESLint、Vitest、四份 Python unittest、`expo-doctor` 和 `npm run build:web`。导入提交对应的 [Actions run 39719383762](https://github.com/MelodyJayai/prayer-earth/actions/runs/39719383762) 结论为 success（约 1 分 35 秒）。仓库内没有部署 workflow。

### 两套产品叠在同一个客户端里

| 表面 | 用户实际看到的 | 数据从哪来 |
| --- | --- | --- |
| 首页、祷告列表、祷告详情、发布 | 4 条种子祷告 + 本机发布 | `src/data.ts` 与 AsyncStorage。远程开关默认关闭 |
| 底部「见证」 | 晨修与宣教图片库，不是种子见证 | Web 优先读 `/api/content`，失败则用随包 `src/contentData.ts`；原生只读随包数据 |
| 「我的 → 管理员入口」 | 跳到 `/admin`（Web）或 `https://prayer.diagport.com/admin`（原生） | 内容管理后台，不是祷告审核台 |

底部导航文案仍是「见证」，路由文件也叫 `testimonies`，Expo 屏标题则是「晨修与宣教」。`src/screens/TestimonyScreen.tsx` 和 `src/data.ts` 里的 `testimonies` 没有被任何路由引用。

### 同工内容（当前线上主线）

- 导入清单 [`docs/content-import-manifest.json`](./content-import-manifest.json)：211 条，其中晨修 122、宣教动态与见证 89；另跳过 3 张重复、1 张已知排除。日期范围 2026-06-08 至 2026-10-17。`src/contentData.ts` 的栏目计数与此一致。有 1 条 ID 以 `mission-` 开头但栏目是晨修（`mission-20260714-022`），清单计数字段按栏目而不是按 ID 前缀。
- 图片在 `assets/content/`，约 431 个文件、203MB，随普通 Git 提交（无 Git LFS、无 `.gitattributes`）。`contentData.ts` 和清单保留微信原始文件名。
- 管理后端是 `scripts/admin_backend.py` + `scripts/admin.html`，由 `scripts/serve-static.py` 挂到同一进程。公开读接口是 `GET /api/content`。管理接口是 `/api/admin/login|session|logout|password|content|users`。能力包括：管理员/编辑角色、首次改密、PBKDF2-HMAC-SHA256（60 万次）、会话 8 小时、HttpOnly + Secure + SameSite=Strict Cookie、CSRF 与同源校验、登录失败限制、写请求限流、图片重编码并去掉元数据、长图按 4096px 分段、草稿/发布/归档、审计表。这不是 `docs/API_CONTRACT.md` 里的 `/v1` 祷告 API。
- 2026-10-22 公网抽查：`/api/content` 返回 200，`version` 为 2，211 条，栏目与日期范围和仓库清单相同，响应里没有 `sourceFile`（有 `sha256`）。`AdminStore` 在首次写入种子时会把 `meta.version` 从 1 加到 2，之后每次内容写入再加。因此这次看到的 version 2 表示种子导入之后没有再次成功写入内容。
- 部署记录见 [`docs/trial-deployment.md`](./trial-deployment.md) 与 [`docs/security-hardening.md`](./security-hardening.md)：OCI 源站只监听 `127.0.0.1:18080`，经 Cloudflare Tunnel 暴露 `https://prayer.diagport.com`。systemd 单元不在仓库里，由 `scripts/deploy-trial.py` 在部署时写到服务器。备份与只读快照的计时器在文档中为每 15 分钟；备份保留 14 份，且文档写明备份仍在源站。
- 备用站 `https://reader.bytelanework.com` 由 `scripts/cf-reader-failover.js` 做 Workers 静态资源兜底，发布脚本是 `scripts/deploy-reader-failover.py`。2026-10-22 读取的 `health.json` 为 `ok: true`、`contentVersion: 2`、晨修 122、宣教 89，`generatedAt` 为 `2026-10-19T10:33:31+00:00`。快照脚本每次生成都会刷新 `generatedAt`。按 15 分钟周期，这个时间戳说明备用站自该时刻起没有发布出新快照。公网无法区分是源站快照计时器停了，还是 Windows 任务 `Prayer-Reader-Snapshot-Publish` 所在电脑停了。主站内容接口当时仍可读取。

### 祷告客户端（路线图主线，默认不联机）

- `.env.example` 与 CI 都把 `EXPO_PUBLIC_API_BASE_URL` 留空，并把 `EXPO_PUBLIC_ENABLE_REMOTE_CONTENT` 设为 `false`。`src/services/startupSync.ts` 在这两个条件不齐时直接返回本地快照。
- 本地存储是 AsyncStorage schema v3（`prayer-earth:state:v3`），含 v2→v3 迁移、最多 100 条祷告、最多 200 条 outbox。发布与「我来祷告」会写入带幂等键的 outbox。`drainOutbox` 按创建顺序发送，退避为 1s / 5s / 30s / 5min / 30min，最多 8 次后进入 `dead`。界面没有 dead-letter「需要处理」的入口。
- `RemotePrayerRepository` 已按契约封装列表、详情、创建、祷告动作、删除、举报和 `POST /v1/outbox/batch`。启动同步只拉一页（`limit: 50`），没有翻页、下拉刷新或增量游标循环。匿名身份客户端会调用 `POST /v1/identities/anonymous` 并保存 refresh token，但没有 refresh 接口；access token 过期后会重新走匿名创建。
- 仓库里不存在实现 `/v1/*` 的服务端。打开远程开关会把客户端指向一个尚未存在的 API，而不是现有的 `/api/content`。
- 种子祷告 4 条，计数是写死的大数（例如 12847），时间戳在模块加载时用 `Date.now()` 现算。个人页「祷告」次数来自本机 `prayedByMe`；「守望天数 18」「关注地区 7」是硬编码。
- 发布页有标题 60 字、正文 500 字、分类，以及社区守则勾选。没有地区、语言、编辑、删除、举报或敏感信息检测。

### 测试

- Vitest：10 个 `*.test.ts`，37 个 `it`。覆盖 reducer、本地仓库、存储迁移、outbox、启动同步、身份 HTTP、内容 feed 解析、格式化。没有组件测试、路由测试或 E2E。
- Python unittest：`scripts/test_admin_backend.py`、`test_generate_reader.py`、`test_reader_publisher.py`、`test_resilience_tools.py`，共 13 个测试方法。覆盖后台种子/上传/最后管理员保护、静态阅读器、发布签名和 SQLite 备份轮转。

## 已实现 vs 缺口

路线图日期是 2026-09-05。它的第 1 节已经承认 Phase 0 的契约/环境/CI 和第 1 批客户端网络边界落地；第 2 节仍写着 schema v2、没有 CI、Vitest 只有 8 个测试、没有后端目录。第 2 节已过时。下面按路线图阶段，用 2026-10-22 的代码核对。

### 已完成或可用

- Phase 0 的文档与客户端边界：`.env.example`、CI、`docs/API_CONTRACT.md` 的领域模型与 `/v1` 路径说明。
- Phase 1 的**客户端**切片：`PrayerRepository`、schema v3 与 v2 迁移、outbox、HTTP 适配器、匿名身份存储、启动同步编排，以及对应单测。默认不启用。
- 路线图未单列、但已经在试用站运行的内容线：微信图片导入脚本、211 条随包内容、栏目/月份/搜索/详情/长图分段、Web 端 `/api/content` 刷新、同工管理后台、静态阅读页、备用站发布脚本和运维文档。

### 进行中（有代码或有线上入口，闭环未完成）

- 内容运营：后台可以发布，但 2026-10-22 的公开版本仍停在种子导入后的 version 2，日期最晚 2026-10-17。备用站健康检查时间停在 2026-10-19。原生 App 不会读后台新内容。
- 祷告同步：客户端会在远程开关打开后做匿名身份、首页拉取和 outbox drain；服务端、token refresh、分页、审核队列和失败可见都不在。
- 容灾：备用站与主站分属文档所述的不同 Cloudflare 账户，能避开 OCI 和 Tunnel，不能避开 Cloudflare 本身。数据库备份按文档留在源站。边缘 WAF / 管理接口限速文档写明尚未用现有 token 配上。

### 未开始（相对路线图）

- Phase 0 验收项：真实运营联系方式、首发市场/语言/年龄/保留期限决策、Bundle ID 与 EAS projectId、三套可区分的 API 环境、指标命名落地。隐私页仍写着「正式发布前，运营方将在此处补充可验证的隐私联系邮箱与官方网站」。
- Phase 1 验收项：两台设备看到同一条已发布祷告、断网后不重复计数、用户删除自己的祷告、审核员追溯祷告处置、`/v1` 鉴权与限流。这些都依赖尚未存在的祷告 API。
- Phase 2：见证核实只能由审核产生、举报/屏蔽/申诉、导出与删号、祷告搜索与分页、用真实历史计算守望天数和关注地区、E2E 与屏幕阅读器测试。
- Phase 3–4：多语言 CMS、推送、分享卡片、运营看板、灰度与实验、异地恢复演练。内容后台只是图片栏目发布，不是这套 CMS。

### 容易误判的遗留物

- `Testimony` 类型上的 `verified: boolean` 在两条未展示的种子里都是 `true`，图片是 Unsplash。关于页仍写「重大见证只有在来源得到核实后才显示核实标记」。当前底部 Tab 不会渲染这两条，但数据还在仓库里。
- `usePrayerStore` 持久化时把 `source === "user" || source === "seed"` 的祷告写入本地快照。种子时间戳每次加载都会变。

## 风险与技术债

1. **产品线混在一起。** 维护者若按 `ROADMAP_UPGRADE.md` 第 2 节或第 6 节「下一轮从 Phase 0 开始」执行，会忽略已经上线的内容站；若把 `/api/content` 当成契约里的祷告 API，客户端远程开关会对不上路径。
2. **公开仓库里的同工内容。** 约 203MB 微信群图片、原始文件名和本地导入路径（清单 `source` 为 `D:\Fight\prayersupdate\WeChatImages\WeChatImages`）在公开 Git 历史中。公开 API 去掉了 `sourceFile`，随包数据和清单没有去掉。仓库无许可证。
3. **基础设施标识写在部署脚本里。** `scripts/deploy-trial.py` 含 OCI SSH 目标、Cloudflare account id、隧道名和本机 token 文件路径。`scripts/deploy-reader-failover.py` 含另一个 Cloudflare account id、zone id、Worker 名，以及 Windows 上的 token 与 SSH 路径。令牌文件匹配 `.gitignore` 的 `.cf-*`，本次核对的 Git 跟踪文件里没有私钥、`.env` 或 sqlite。标识本身已经公开，轮换与访问控制不能假设「仓库是私有的」。
4. **备用发布链的公开证据已停在 2026-10-19。** 主站内容接口在 2026-10-22 仍返回与仓库相同的 211 条。文档中的 15 分钟镜像不能当作当前仍在自动更新。
5. **上架与 UGC。** 占位 Bundle ID、无 EAS projectId、隐私联系方式占位、祷告计数不可信、没有举报/屏蔽/删号、社区守则只约束本机发布。按路线图和 `docs/trial-status.md`，都不满足公开 UGC 或商店提交。管理入口放在所有用户的「我的」页，后台安全依赖登录而不是隐藏 URL。
6. **客户端远程路径未接通，且失败态不完整。** outbox 可以进入 `dead`，UI 不展示。只合并第一页 50 条。refresh token 只存储。`EXPO_PUBLIC_ENABLE_ANALYTICS` 在示例和 CI 中为 false，仓库里也没有对应上报实现。
7. **测试与历史。** CI 在导入提交上是绿的，覆盖的是单测和脚本回归，不是真机、无障碍或双机同步。单提交历史意味着线上行为和文档冲突时，无法用 Git 追溯是谁在何时改的。

## 建议维护优先级

1. **先写下一份只做一件事的范围说明。** 若接手的是试用站：只维护内容发布、主站可用性和备用阅读，祷告 Tab 保持离线演示并在界面上避免被理解成全球实时计数。若接手的是路线图社区：内容站继续按现有后台运转，但不要把祷告 `/v1` 塞进 `admin_backend.py`。两套同时做成「一个后端」会把契约和现有同工流程缠在一起。
2. **当天核对备用发布是否还在跑。** 以 `reader.bytelanework.com/health.json` 的 `generatedAt` 是否晚于 2026-10-19T10:33:31Z 为准，并在源站看 `prayer-earth-trial-snapshot.timer`、在发布电脑看任务 `Prayer-Reader-Snapshot-Publish`。内容本身不必先改。
3. **补上文档已经点名的两处运维缺口：源站数据库的异地私有备份，以及 Cloudflare 之外的第二份静态托管。** 边缘 WAF 和管理接口限速仍要由拥有该 zone 安全权限的人在控制台配置，仓库里的应用层限流不能代替它。
4. **处理公开仓库中的微信图片与原始文件名。** 决定这些文件是否继续留在公开 Git 里；至少不要再把新的原始文件名写入 `src/contentData.ts` 和清单后推到公开分支。部署脚本中的主机、账号 ID 和本机密钥路径改到未跟踪的本地配置，再考虑轮换已经出现在 Git 历史中的访问路径。
5. **在祷告 API 真正存在之前，保持 `EXPO_PUBLIC_ENABLE_REMOTE_CONTENT=false` 且 API 基址为空。** 现有管理后台不能充当该开关的服务端。
6. **商店或公开 UGC 之前单独列一张阻断清单，而不是继续加页面。** 阻断项是：自有 Bundle ID、EAS projectId、可验证的隐私联系方式、去掉或停用未核实却标记为已核实的种子见证、祷告计数改为明确的本机演示、用户删除/举报/审核闭环。这些都还没有代码落点。
7. **若下一轮开发确实是祷告 MVP，只做契约里的垂直切片。** 服务端实现匿名身份、`POST /v1/prayers`、祷告动作、软删除和一条审核记录；客户端补 refresh、第一页之后的游标，以及 dead-letter 可见。完成标准沿用路线图：两台设备能看到同一条已发布祷告，断网重试不重复计数。在此之前不做推送、多语言 CMS 和推荐。

## 关键路径

- 仓库：https://github.com/MelodyJayai/prayer-earth
- 试用站：https://prayer.diagport.com
- 主站轻量阅读：https://prayer.diagport.com/reader/index.html
- 管理入口：https://prayer.diagport.com/admin
- 公开内容：https://prayer.diagport.com/api/content
- 备用站：https://reader.bytelanework.com
- 备用健康检查：https://reader.bytelanework.com/health.json
- CI：https://github.com/MelodyJayai/prayer-earth/actions/runs/39719383762
- 路线图：[`ROADMAP_UPGRADE.md`](../ROADMAP_UPGRADE.md)（第 2 节过时）
- 契约：[`docs/API_CONTRACT.md`](./API_CONTRACT.md)
- 试用状态：[`docs/trial-status.md`](./trial-status.md)
- 客户端远程开关：[`src/services/runtimeConfig.ts`](../src/services/runtimeConfig.ts)、[`src/services/startupSync.ts`](../src/services/startupSync.ts)
- 内容后台：[`scripts/admin_backend.py`](../scripts/admin_backend.py)
- 部署：[`scripts/deploy-trial.py`](../scripts/deploy-trial.py)、[`scripts/deploy-reader-failover.py`](../scripts/deploy-reader-failover.py)
