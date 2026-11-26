# 宣教动态·报告·会议板块

和「需要祷告」并列的第二个板块，页面是 `/missions`（与 `/prayers` 页顶部互相切换）。收录大型区域性宣教会议、宣教进展和研究报告，只显示标题、短摘要、日期、地区、类型和来源链接，不转载全文。

## 接口

`POST /api/ingest/missions`，鉴权、速率限制、1–30 条、64 KiB 上限和 `verified` 自动公开开关都与 `POST /api/ingest/news` 相同（同一把提交密钥，同一个 10 分钟 8 次的限额）。

```json
{
  "items": [
    {
      "title": "洛桑运动区域会议",
      "summary": "短摘要，不超过 400 个字符，不要放全文。",
      "source_url": "https://example.com/missions/conference",
      "source_name": "洛桑运动",
      "published_at": "2026-11-20T08:00:00Z",
      "region": "非洲",
      "verified": false,
      "kind": "会议",
      "event_date": "2026-12-01"
    }
  ]
}
```

| 字段 | 约束 |
| --- | --- |
| `title` | 1–120 个字符 |
| `summary` | 1–400 个字符 |
| `source_url` | 仅 `http` 或 `https`，规则同宗教动态 |
| `source_name` | 1–60 个字符 |
| `published_at` | 同宗教动态（UTC 日期，不能晚于当前时间 36 小时） |
| `region` | 1–40 个字符 |
| `verified` | JSON 布尔值。`true` 且自动公开开着，提交时直接公开；`false` 先进待审，同工在后台「宣教动态」页公开后才显示，页面标为「待核实」 |
| `kind` | 只能是 `会议`、`进展`、`报告` |
| `event_date` | 选填，`YYYY-MM-DD`，活动日期，可以晚于今天（例如即将举行的会议） |

多出来的字段（包括 `category`）会使整批失败。编号是 `mission-<YYYYMMDD>-<来源链接 SHA-256 前 12 位>`，相同编号用 `INSERT OR IGNORE`：已存在则忽略，已驳回的不会被重新公开。返回 `{"inserted": [...], "ignored": [...], "published": [...]}`。

## 公开读取与后台

- `GET /api/missions`：已公开条目，`{version, items}`，缓存 30 秒，与 `/api/content` 共用内容版本号。
- 后台 `https://prayer.diagport.com/admin` 新增「宣教动态」页：按状态查看，逐条公开、驳回或撤下。
- 宣教动态与宗教动态、需要祷告完全分开：不会进入 `/api/content`、`/api/prayer-requests`、轻量阅读页或备用站快照。

## 首批内容

`docs/missions-first-batch.json` 是首批 13 条（6 条已核实、7 条待核实），全部来自已发布的日更，每条都带可核验链接。部署后用提交密钥一次提交即可，重复提交会被忽略。

## 暂未覆盖

- `/reader/*` 的免脚本阅读页和备用站快照还没有宣教动态板块。
- 原生 App 没有该板块，只有网页版。
