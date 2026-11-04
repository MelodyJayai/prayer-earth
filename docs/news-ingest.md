# 宗教动态接入

外部汇总 bot 每个整点把基督教、宗教宣教、教会相关的短讯一次性提交到主站。条目先进入待审，同工在后台公开或驳回。只有公开的短讯进入主应用、轻量阅读页和备用站快照。页面只显示标题、短摘要、来源和日期，不转载全文。

## 接口

`POST /api/ingest/news`

鉴权头：

```http
Authorization: Bearer <ingest-key>
Content-Type: application/json
```

不使用管理员登录，也不读取管理员 cookie。请不要把密钥放在 URL 里。

请求体只接受 `items` 数组。单次 1–30 条，请求体最大 64 KiB。同一来源 IP 每 10 分钟最多 8 次（含失败请求）。

```json
{
  "items": [
    {
      "title": "教会周报",
      "summary": "短摘要，不超过 400 个字符，不要放全文。",
      "source_url": "https://example.com/church/weekly",
      "source_name": "教会通讯",
      "published_at": "2026-10-27T08:00:00Z",
      "region": "全球",
      "verified": false,
      "category": "基督教"
    }
  ]
}
```

字段：

| 字段 | 约束 |
| --- | --- |
| `title` | 1–120 个字符，不能含控制字符 |
| `summary` | 1–400 个字符 |
| `source_url` | 仅 `http` 或 `https`，最长 500。拒绝 `javascript:`、`file:`、用户名密码和反斜杠。片段（`#...`）不参与去重 |
| `source_name` | 1–60 个字符 |
| `published_at` | `YYYY-MM-DD` 或带时区的 ISO-8601。按 UTC 日期编号，不能早于 1990，也不能晚于当前时间 36 小时 |
| `region` | 1–40 个字符 |
| `verified` | JSON 布尔值。`false` 会在页面上显示「待核实」 |
| `category` | 只能是 `基督教`、`宗教宣教`、`教会`、`教会相关` |

多出来的字段（包括全文 `body`）会使整批失败，本批一条都不会写入。`财经`、`AI`、`安全` 以及其他非白名单分类同样整批拒绝。

编号是 `news-<YYYYMMDD>-<来源链接 SHA-256 的前 12 位十六进制>`。链接会先规范成小写协议和主机、去掉片段和默认端口。相同编号使用 `INSERT OR IGNORE`：已存在则忽略，不覆盖待审、已公开或已驳回的记录。

成功时 HTTP 200：

```json
{
  "inserted": ["news-20261027-0123456789ab"],
  "ignored": []
}
```

失败时正文是 `{ "error": "<code>", "message": "<说明>" }`，不会回显密钥。

| HTTP | `error` | 含义 |
| --- | --- | --- |
| 200 |  | 校验通过。重复编号在 `ignored` 里，不是错误 |
| 400 | `invalid_batch` / `invalid_news_item` / `invalid_text` / `invalid_source_url` / `invalid_category` / `invalid_verified` / `invalid_published_at` / `unknown_field` / `batch_too_large` | 整批拒绝 |
| 401 | `invalid_ingest_key` | 密钥缺失或错误 |
| 404 |  | 服务器没有配置密钥，入口关闭，表现与不存在的路径相同 |
| 405 | `method_not_allowed` | 入口已开启但不是 POST |
| 413 | `request_too_large` | 超过 64 KiB |
| 415 | `json_required` | 不是 JSON 对象 |
| 429 | `ingest_rate_limited` | 超过每 10 分钟 8 次。响应带 `Retry-After: 600` |
| 503 | `ingest_unavailable` | 配置了密钥来源但文件缺失、过短、过长或无法读取 |

## 密钥放在哪里

密钥不要写入仓库、部署脚本、数据库或日志。长度 16–256，且不能含控制字符。建议使用一行十六进制：

```sh
openssl rand -hex 32
```

两种放法，进程启动后每次请求都会重新解析，优先级如下。

1. 环境变量 `PRAYER_NEWS_INGEST_KEY`。`deploy-trial.py` 生成的 `prayer-earth-trial.service` 含有 `EnvironmentFile=-/etc/prayer-earth-news/ingest.env`。文件不存在时服务仍能启动，入口保持关闭。需要这种放法时，由管理员在服务器上单独创建文件，不要让部署脚本生成它：

   ```sh
   sudo install -d -o root -g prayer-web -m 750 /etc/prayer-earth-news
   sudo install -o root -g root -m 600 /dev/null /etc/prayer-earth-news/ingest.env
   printf 'PRAYER_NEWS_INGEST_KEY=%s\n' "$(openssl rand -hex 32)" | sudo tee /etc/prayer-earth-news/ingest.env >/dev/null
   sudo systemctl restart prayer-earth-trial.service
   ```

   systemd 在降权前读取这个文件。文件应为 `root:root`、模式 `600`。十六进制密钥可以避开 `%` 这类单元说明符。改环境变量后必须重启服务。

2. 密钥文件。未设置上面的环境变量时，若设置了 `PRAYER_NEWS_INGEST_KEY_FILE`，就读取该路径；否则在 `/etc/prayer-earth-news/ingest.key` 存在时读取它。文件由 `prayer-web` 在请求时读取，所以目录保持 `root:prayer-web` `750`，文件为 `root:prayer-web` `640`，内容只有一行密钥。这种放法替换文件后下一次请求即生效，不必为了轮换而重启。路径已指定但文件缺失或不可读时返回 503，而不是假装入口不存在。

`ProtectSystem=strict` 下 `/etc` 仍可读。不要把密钥放进 `/opt/prayer-earth-trial/data`，那个目录是服务可写的。

轮换：生成新密钥，先把它交给提交方 bot，再替换环境文件或密钥文件。环境变量方式随后执行 `sudo systemctl restart prayer-earth-trial.service`。确认新密钥可以提交后，删除旧文件内容。旧密钥立即失效，已入库的动态不受影响。

## 审核、版本和备用站

新行的 `status` 是 `pending`。待审和驳回不会出现在：

- `GET /api/content`
- 主站 `/reader/` 页面
- `snapshots/current` 或备用站上传内容

因此待审提交不会增加内容 `version`，也不会改变快照文件哈希。备用站签名覆盖内容文件哈希和内容版本，不覆盖 `health.json` 的 `generatedAt`。待审阶段签名不变，发布任务会核对后跳过部署。

同工登录后，在「宗教动态」里公开或驳回。这两个动作沿用管理接口的会话 cookie、`X-CSRF-Token` 和同源检查；编辑同工和管理员都可以审核，但必须先改掉临时密码。写请求仍走原来的管理员写限流。

- 待审 → 公开：写入公开列表，`version` 加 1
- 待审 → 驳回：仍不公开，`version` 不变
- 已公开 → 驳回：从公开列表移除，`version` 加 1
- 重复执行同一动作：不重复加版本

`GET /api/admin/news` 在 `items` 之外多一个 `publishable`：当前 `status=pending` 且 `verified` 为 JSON 布尔值 `true` 的条数。字符串 `"false"` / `"true"`、数字、缺失字段都不算。列表筛选不会改变这个数字。

### 一键公开已核实

页面按钮是「一键公开已核实」。`publishable` 为 0 时按钮禁用，并提示没有已核实的待审动态。大于 0 时按钮写上条数。点击后先向服务端再取一次条数，确认框里显示将要公开的条数；取消则不提交。确认后才调用下面的接口，并把该条数作为 `expected_count`。

`POST /api/admin/news/publish-verified`

需要已登录的会话 cookie、`X-CSRF-Token`、与单条审核相同的同源检查。临时密码状态下返回 `password_change_required`，不会改数据。编辑同工和管理员都可以调用。

```json
{ "expected_count": 51 }
```

`expected_count` 可以不传。传了就必须是非负整数，且等于当时严格可公开的条数。JSON 布尔值 `true`/`false` 不算整数。多出来的字段会被拒绝。

只处理同时满足这两点的行：`status` 是 `pending`，且存下来的 `verified` 解析后是布尔值 `true`。`verified` 为 `false`、字符串 `"false"` 或 `"true"`、数字、缺失、坏掉的 JSON，以及 `rejected`、已经 `published` 的行，都保持原样。

成功时 HTTP 200。有可公开条目时，在同一个数据库事务里把这些行改成 `published`，内容 `version` 只加 1（不论条数多少），并写一条审计。没有可公开条目时不增加 `version`，仍然写一条 `published` 为 0 的审计。

```json
{ "published": 51, "version": 12 }
```

审计的 `action` 是 `publish_verified_news`，`actor` 是操作人 id，`detail` 是 `{ "published": 51, "ids": ["news-..."] }`。条数对不上时返回 409，不改任何行、不加版本、不写这条审计：

```json
{
  "error": "count_mismatch",
  "message": "待公开条数已变为 50，请重新确认。",
  "actual": 50
}
```

页面收到 409 后用 `actual` 再确认一次。第二次仍不一致时，只显示错误，不会公开一部分。事务中途失败也会整批回滚。

| HTTP | `error` | 含义 |
| --- | --- | --- |
| 200 |  | 已按服务端实际条数处理。`published` 为 0 时版本不变 |
| 400 | `unknown_field` / `invalid_expected_count` | 多余字段，或期望条数不是非负整数 |
| 401 | `authentication_required` | 未登录 |
| 403 | `invalid_csrf` / `invalid_origin` / `password_change_required` | 与其他管理写接口相同 |
| 409 | `count_mismatch` | `expected_count` 与实际可公开条数不一致。响应里的 `actual` 是实际条数 |
| 429 | `write_rate_limited` | 管理员写请求过于频繁 |

公开后的下一次快照会多出文字页和来源链接，文件哈希与 `version` 一起变化，签名变化，备用站发布任务会部署新快照。一键公开 N 条（N > 0）也只加 1 次版本、产生一次新签名，不会按条数连加。N 为 0 时快照签名不变，备用站不会因此发布。来源链接只允许 `http`/`https`。阅读页把文本做 HTML 转义，链接使用 `target="_blank"` 和 `rel="noopener noreferrer"`。

公开错了没有批量撤回。在「宗教动态」里对已公开条目逐条点「驳回」。每一条从已公开变为驳回都会再把 `version` 加 1，备用站会再发一版，该条从主应用和备用阅读站消失。其余已公开条目不受影响。

## 需要祷告

祷告页不再使用 4 条种子。它读取已公开、并且被分流到祷告页的宗教动态。这是展示层分流：行仍留在 `news` 表里，不删除。

分流规则（同时满足才进入祷告页，并从宗教动态列表移出）：

1. `status` 是 `published`
2. `prayer_excluded` 不是 1
3. 并且下面任一成立：
   - `needs_prayer` 是 1（同工手动标记）
   - `verified` 是 JSON 布尔值 `true`，且标题或摘要命中关键词（自动放行）

关键词只匹配标题和摘要，不看地区、来源名或链接，避免过宽。表在 `scripts/admin_backend.py` 的 `PRAYER_CANDIDATE_KEYWORDS`：迫害、逾捕、监禁、袭击教会、杀害、绑架、禁教、拘留、关闭教会、拘押、persecution。英文不区分大小写。`verified` 为字符串 `"true"`、数字或缺失时不算已核实，不会自动放行。

未核实的条目即使命中关键词也不会自动出现。同工在「迫害筛选」里点「设为需要祷告」后才会进入祷告页，主应用标「待核实」。待审条目点这个按钮会在同一次写入里公开。已经排除的条目再点「设为需要祷告」会清掉排除。

「排除」把 `prayer_excluded` 设为 1。排除优先于自动放行，也优先于当时的手动标记：条目离开祷告页；若仍是已公开，就回到宗教动态列表。取消排除后，仍符合自动规则或仍有手动标记的条目会重新进入祷告页。取消手动标记不会取消排除；若它仍是未排除的已核实候选，自动规则继续生效，应改点「排除」。

旧库在进程打开数据库时自动升级：缺列就 `ALTER TABLE` 增加 `needs_prayer` 和 `prayer_excluded`，默认 0，不改已有 JSON、状态或内容版本。升级前先备份 `data/`。

### 公开读接口

`GET /api/prayer-requests` 和 `HEAD`。不需要登录。只返回已分流的条目，按 `date`、`id` 从新到旧：

```json
{
  "version": 12,
  "items": [
    {
      "id": "news-20261027-0123456789ab",
      "title": "标题",
      "summary": "短摘要",
      "sourceName": "来源名",
      "sourceUrl": "https://example.com/story",
      "date": "2026-10-27",
      "region": "地区",
      "verified": false
    }
  ]
}
```

`id` 只用于本机记住「你已为此祷告」，不是管理字段。响应里没有 `status`、`needsPrayer`、`prayerExcluded`、`prayerCandidate`。`version` 与 `GET /api/content` 的 `version` 是同一个计数。缓存、`ETag`（`prayer-requests-<version>`）、`X-Content-Type-Options` 和 `Referrer-Policy` 与 `/api/content` 相同。其他方法返回 405。写请求限流不作用在这个 GET 上。

这些条目不会出现在 `GET /api/content`、主应用「动态」、`/reader/news.html`、`/reader/index.html` 的全部列表，以及备用站快照的对应页面。它们出现在主应用祷告页、`/reader/prayers.html` 和备用站的「需要祷告」。来源仍是 `http`/`https`，`target="_blank"` 与 `rel="noopener noreferrer"`。

宗教动态列表或祷告页的成员变化时，内容 `version` 加 1，并且只加 1。因此 `/api/content` 的 ETag、快照 `contentVersion` 和阅读页 HTML 一起变，备用站签名跟着变。成员没变（重复标记、重复排除、待审入库）不加版本。只驳回一条原本不在任一公开列表的待审，版本也不加。

`POST /api/admin/news/<id>/prayer`，正文只能是 `{ "needs_prayer": true }` 或 `{ "needs_prayer": false }`。`POST /api/admin/news/<id>/prayer-exclusion`，正文只能是 `{ "excluded": true }` 或 `{ "excluded": false }`。会话、`X-CSRF-Token`、同源检查、临时密码限制和写限流与单条审核相同。编辑同工和管理员都可以操作。布尔值不能写成字符串。

主应用用同源 `GET /api/prayer-requests`，不打开 `EXPO_PUBLIC_ENABLE_REMOTE_CONTENT`。接口失败或列表为空时分别显示「暂时无法读取需要代祷的动态」和「暂无需要代祷的动态」，不用种子顶上。代祷人数不由服务端提供；「我来祷告」只写在本机。本机发布的祷告仍留在 AsyncStorage，旧的 v3 快照（含曾经存下的种子）升级时不丢。

备用阅读页导航增加「需要祷告」。即使还没有分流条目，下一次快照的各页导航也会变，从而产生一次新签名。发布脚本原有的 http/https 外链放行已经覆盖祷告页上的来源链接，不需要再放宽；`javascript:` 仍然拒绝。没有 `prayers.html` 的旧快照仍能通过校验。

备用站 Worker 没有改。`/admin`、`/api/content` 仍然不是静态文件，请求落到 Worker 后继续是 404；其他方法继续是 405。发布脚本只放行文字动态上的外链来源，不放行 `javascript:`、协议相对链接或脚本。`/admin` 和 `api/content` 也仍然不能作为快照路径。

部署本功能后，阅读页导航会多出「宗教动态」，即使还没有公开动态，下一次快照的 HTML 也会变，从而产生一次新签名。那次发布之后，仅有待审或驳回记录不会再改变签名。

## 主应用

Web 仍先读 `/api/content`，失败时继续使用随包图片。原生端不请求该接口，只显示随包的图片内容。文字动态没有图片分段，列表、详情、搜索和月份筛选仍按原规则处理晨修与宣教图片。动态栏目只渲染标题、摘要、来源、日期和「待核实」。

## 测试与本地验证

与 CI 相同的检查：

```sh
npm run typecheck
npm run lint
npm test
python -m unittest scripts.test_admin_backend scripts.test_generate_reader scripts.test_resilience_tools scripts.test_reader_publisher scripts.test_import_wechat_source scripts.test_serve_static
npm run build:web
```

本地手动看一条动态：

```sh
mkdir -p .local-data
printf '%s\n' 'local-ingest-key-01' > .local-data/news-ingest.key
chmod 600 .local-data/news-ingest.key
PRAYER_NEWS_INGEST_KEY_FILE=$PWD/.local-data/news-ingest.key \
  python scripts/serve-static.py --directory dist --data-directory .local-data --insecure-cookie
```

另开终端提交，并确认公开前读不到正文：

```sh
curl -s -H "Authorization: Bearer local-ingest-key-01" -H 'Content-Type: application/json' \
  -d '{"items":[{"title":"教会周报","summary":"短摘要","source_url":"https://example.com/church","source_name":"教会通讯","published_at":"2026-10-27T08:00:00Z","region":"全球","verified":false,"category":"基督教"}]}' \
  http://127.0.0.1:18080/api/ingest/news
curl -s http://127.0.0.1:18080/api/content
```

然后用同工账号打开 `/admin`，在「宗教动态」里公开。再次请求 `/api/content` 应能看到该条，`/reader/news.html` 应有摘要、来源链接和「待核实」，晨修列表不应出现它。错误密钥应得到 401，不配置密钥时应得到 404。

`.local-data/` 只留在本机，不要提交。

## 上线前检查

- 仓库、脚本、镜像和日志里没有真实密钥。`deploy-trial.py` 只声明可选的 `EnvironmentFile`，不写密钥。
- 服务器上的密钥文件权限是 `600`（环境文件）或 `640` 且属组为 `prayer-web`（密钥文件）。提交方 bot 已换成同一把密钥。
- 用错误密钥、非宗教分类、超长摘要和 `javascript:` 链接各试一次，确认被拒绝且没有入库。
- 待审时记下 `/api/content` 的 `version` 和备用站 `health.json` 的 `contentVersion`。两者都不应因为这次提交而增加。
- 公开一条之后，`version` 增加，主站阅读页和稍后的备用站都能看到摘要与来源，待审和驳回的仍不可见。
- 一键公开前记下 `GET /api/admin/news` 的 `publishable`，以及 `/api/content` 的 `version`。确认框里的条数应与 `publishable` 一致。只点一次并确认后，`version` 只加 1；`verified` 不是布尔值 `true` 的待审、已驳回和原先已公开的条目状态不变。条数为 0 时按钮不可用，直接调用接口也不会增加 `version`。
- 若要撤回，在后台对不该公开的条目逐条驳回，并确认每驳回一条 `version` 再加 1、该条从公开列表消失。
- 数据库迁移前备份 `/opt/prayer-earth-trial/data`（至少包含 `admin.sqlite3`）。打开服务后旧库应自动多出 `needs_prayer` 和 `prayer_excluded`，已有行仍在，两列默认为 0。
- 用一条测试动态确认：已核实且标题含「迫害」一类关键词的，公开后出现在 `/api/prayer-requests` 和 `/reader/prayers.html`，不出现在 `/api/content` 和 `/reader/news.html`。排除后回到后两处，祷告页不再列出，数据库里仍能看到该行。未核实的同类标题不会自动出现，手动标记后才出现并带「待核实」。
- `GET /api/content` 与快照 `health.json` 的 `contentVersion` 在同一次分流后相等，并且只加 1。备用站签名应变化。`/api/prayer-requests` 的响应里没有 `status` 或 `needsPrayer`。
- 备用站上 `/admin` 与 `/api/content` 仍是 404，POST 仍是 405。`/reader/prayers.html` 在新快照里应可打开；来源链接仍只接受 http/https。
- 发布机上的 `deploy-reader-failover.py` 要先于第一条带外链的动态更新。旧校验器会拒绝外部来源链接，失败时会保留上一份完整快照。
- 现有图片库（`assets/content`、`docs/content-import-manifest.json`、`src/contentData.ts`）不应有改动。
- 部署仍会整目录替换 `/opt/prayer-earth-trial/site`。`/opt/prayer-earth-trial/data`（含 `admin.sqlite3` 和上传图片）不在替换范围内，新闻行写在这个库的 `news` 表里，备份任务会随 SQLite 一致性备份带走。
