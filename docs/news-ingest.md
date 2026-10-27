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

同工登录后，在「宗教动态」里公开或驳回。这两个动作沿用管理接口的会话 cookie、`X-CSRF-Token` 和同源检查；编辑同工和管理员都可以审核，但必须先改掉临时密码。

- 待审 → 公开：写入公开列表，`version` 加 1
- 待审 → 驳回：仍不公开，`version` 不变
- 已公开 → 驳回：从公开列表移除，`version` 加 1
- 重复执行同一动作：不重复加版本

公开后的下一次快照会多出文字页和来源链接，文件哈希与 `version` 一起变化，签名变化，备用站发布任务会部署新快照。来源链接只允许 `http`/`https`。阅读页把文本做 HTML 转义，链接使用 `target="_blank"` 和 `rel="noopener noreferrer"`。

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
python -m unittest scripts.test_admin_backend scripts.test_generate_reader scripts.test_resilience_tools scripts.test_reader_publisher
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
- 备用站上 `/admin` 与 `/api/content` 仍是 404，POST 仍是 405。
- 发布机上的 `deploy-reader-failover.py` 要先于第一条带外链的动态更新。旧校验器会拒绝外部来源链接，失败时会保留上一份完整快照。
- 现有图片库（`assets/content`、`docs/content-import-manifest.json`、`src/contentData.ts`）不应有改动。
- 部署仍会整目录替换 `/opt/prayer-earth-trial/site`。`/opt/prayer-earth-trial/data`（含 `admin.sqlite3` 和上传图片）不在替换范围内，新闻行写在这个库的 `news` 表里，备份任务会随 SQLite 一致性备份带走。
