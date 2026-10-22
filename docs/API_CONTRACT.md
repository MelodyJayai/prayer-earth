# Prayer Earth Phase 0 API 契约

> 文档版本：v0.1（Phase 0 评审稿）  
> 适用范围：线上 MVP 的领域模型、客户端 repository 与离线 outbox。  
> 供应商无关：Supabase、Firebase 或自建 API 均必须实现同一份契约。

## 1. 约定

- API 根路径为 `/v1`，请求和响应使用 JSON，时间统一为 UTC ISO-8601（例如 `2026-09-05T08:30:00Z`）。
- 所有资源 ID 使用不可猜测的 UUID/ULID 字符串；客户端不能依赖数据库自增 ID。
- `createdAt`、`updatedAt`、`version` 和审计字段由服务端生成，客户端提交的时间只作为 `clientCreatedAt` 留存。
- 除公开读取接口外均需要 `Authorization: Bearer <access-token>`。匿名用户首次启动时由 `POST /v1/identities/anonymous` 换取短期 access token 和可轮换 refresh token。
- 写请求必须带 `Idempotency-Key`（客户端生成 UUID，建议与 outbox event 的 `idempotencyKey` 相同）。服务端至少保留 24 小时的幂等结果；同 key 不同请求体返回 `409 IDEMPOTENCY_KEY_REUSED`。
- 错误响应统一为：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数无效",
    "requestId": "req_01J...",
    "retryable": false,
    "fieldErrors": { "title": "最多 60 个字符" }
  }
}
```

`requestId` 用于客户端日志和审核追踪；客户端只向用户展示可本地化的错误 code，不直接展示内部堆栈。

## 2. 通用响应与分页

列表响应使用统一形状，游标是不透明字符串，不允许客户端解码或自行拼接：

```json
{
  "data": [/* resource */],
  "page": { "limit": 20, "nextCursor": "eyJjcmVhdGVkQXQiOi..." }
}
```

`limit` 范围 1–50，默认 20。默认按 `createdAt DESC, id DESC` 排序；服务端在生成游标时固定过滤条件和排序，避免新增内容导致重复。没有下一页时 `nextCursor` 为 `null`。需要刷新时客户端丢弃旧游标并重新请求第一页。

资源中的 `prayedByMe`、`canEdit`、`canDelete` 是按当前身份计算的派生字段，不写回公共资源。

## 3. 领域模型

### 3.1 Prayer

```ts
type Prayer = {
  id: string;
  title: string;                 // 1–60 字符
  excerpt: string;               // 1–500 字符；服务端可生成预览
  body?: string;                 // 可选，最多 5,000 字符
  category: "和平" | "医治" | "家庭" | "教会";
  urgent: boolean;
  location?: { countryCode?: string; admin1?: string; city?: string; displayName: string };
  locale: string;                // BCP-47，如 zh-CN、en
  authorIdentityId?: string;     // 对匿名作者仅返回 null 或 publicAuthor
  publicAuthor?: { displayName?: string; avatarUrl?: string };
  source: "seed" | "user";
  status: "pending" | "published" | "rejected" | "hidden" | "deleted";
  moderationState: "not_required" | "queued" | "approved" | "rejected" | "hidden";
  prayerCount: number;           // 服务端原子计数，非负
  prayedByMe: boolean;
  canEdit: boolean;
  canDelete: boolean;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
  deletedAt?: string;
  version: number;               // 乐观并发控制，从 1 开始
};
```

新用户祷告先进入 `pending/queued`；审核通过后转为 `published/approved` 才出现在公共列表。`deleted` 为软删除终态，公共接口不返回正文，但审计记录保留。

### 3.2 Testimony

```ts
type Testimony = {
  id: string;
  title: string;                 // 1–100 字符
  excerpt: string;               // 1–1,000 字符
  body?: string;                 // 最多 10,000 字符
  location?: { countryCode?: string; admin1?: string; city?: string; displayName: string };
  locale: string;
  authorIdentityId?: string;
  image?: { url: string; alt?: string; credit?: string; license?: string };
  sourceAttribution?: { kind: "first_party" | "user_submitted" | "external"; reference?: string };
  verification: "unverified" | "in_review" | "verified" | "rejected";
  status: "pending" | "published" | "hidden" | "deleted";
  moderationState: "queued" | "approved" | "rejected" | "hidden";
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
  verifiedAt?: string;
  verifiedBy?: string;
  canEdit: boolean;
  canDelete: boolean;
  version: number;
};
```

`verification=verified` 只能由审核动作产生，并且必须有 `verifiedBy`、`verifiedAt` 和来源/证据引用；客户端不可自行设置该值。当前 `src/data.ts` 中的图片和 seed 见证迁移到正式环境前必须补齐授权与来源。

### 3.3 Identity（User/AnonymousIdentity）

```ts
type Identity = {
  id: string;
  kind: "anonymous" | "account";
  authProviders: Array<"anonymous" | "email" | "apple" | "google">;
  displayName?: string;
  locale?: string;
  countryCode?: string;
  status: "active" | "suspended" | "deleted";
  consentVersion?: string;
  createdAt: string;
  updatedAt: string;
  lastSeenAt?: string;
};
```

匿名身份不要求邮箱或真实姓名；绑定账号时保持 `id` 不变，避免祷告、举报和 outbox 归属丢失。`deleted` 身份的个人资料立即清空，内容按保留策略匿名化或软删除。

### 3.4 Report

```ts
type Report = {
  id: string;
  reporterIdentityId: string;
  targetType: "prayer" | "testimony" | "identity";
  targetId: string;
  reason: "spam" | "harassment" | "self_harm" | "violence" | "privacy" | "copyright" | "misinformation" | "other";
  details?: string;               // 最多 2,000 字符，避免收集额外敏感信息
  status: "open" | "triaged" | "actioned" | "dismissed" | "duplicate";
  priority: "low" | "normal" | "high" | "critical";
  moderationReviewId?: string;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string;
};
```

同一举报人对同一目标和 reason 在 24 小时内视为重复；服务端仍返回原 `reportId`，防止离线重试产生多条工单。

### 3.5 ModerationReview

```ts
type ModerationReview = {
  id: string;
  targetType: "prayer" | "testimony" | "identity";
  targetId: string;
  action: "approve" | "reject" | "hide" | "restore" | "suspend";
  reasonCode: string;
  note?: string;
  evidenceRefs?: string[];
  reviewerIdentityId: string;
  createdAt: string;
  effectiveAt: string;
};
```

审核动作是追加式、不可编辑的审计事件；更正通过新建一条 review。内容最终状态由资源状态和最新有效 review 共同决定。

### 3.6 OutboxEvent

```ts
type OutboxEvent = {
  id: string;
  aggregateType: "prayer" | "testimony" | "prayer_action" | "report" | "identity";
  aggregateId?: string;
  eventType: "prayer.create" | "prayer.pray" | "prayer.unpray" | "prayer.delete" | "testimony.create" | "report.create" | "identity.upgrade";
  payload: Record<string, unknown>;
  idempotencyKey: string;
  status: "pending" | "in_flight" | "succeeded" | "failed" | "dead";
  attempts: number;
  nextAttemptAt?: string;
  lastErrorCode?: string;
  createdAt: string;
  updatedAt: string;
};
```

客户端本地 outbox 只保存执行所需的最小 payload，不保存 access token。队列按 `createdAt` 顺序发送；网络错误采用指数退避（1s、5s、30s、5m、30m，最多 8 次），4xx 非可重试错误转为 `dead` 并在 UI 显示“需要处理”。服务端成功响应或幂等命中都将事件标为 `succeeded`。

## 4. MVP 接口

| 方法与路径 | 用途 | 关键约束 |
| --- | --- | --- |
| `POST /v1/identities/anonymous` | 创建/恢复匿名身份 | 设备安装 ID 仅作恢复提示，服务端仍签发新 token |
| `GET /v1/me` | 当前身份与权限 | 返回 `Identity`、数据保留/同意版本 |
| `GET /v1/prayers?cursor=&limit=&category=&urgent=&locale=&country=` | 公共祷告列表 | 仅 `status=published`；游标分页 |
| `GET /v1/prayers/{id}` | 祷告详情 | 可返回作者自己的 pending 内容 |
| `POST /v1/prayers` | 创建祷告 | `Idempotency-Key`；默认 pending；服务端校验长度、链接和风险词 |
| `DELETE /v1/prayers/{id}` | 删除自己的祷告 | 仅作者或管理员；软删除；支持 `If-Match: version` |
| `POST /v1/prayers/{id}/prayer-action` | 设置“我已祷告” | body `{ "prayed": true|false }`；按身份唯一，重复请求幂等 |
| `GET /v1/testimonies?cursor=&limit=&locale=&country=` | 见证列表 | 默认仅 published；`verification` 作为筛选 |
| `GET /v1/testimonies/{id}` | 见证详情 | 返回来源、授权与核实元数据 |
| `POST /v1/reports` | 举报内容/身份 | `Idempotency-Key`；重复举报返回原记录 |
| `POST /v1/outbox/batch` | 批量同步离线事件 | 单批最多 50 个事件；逐事件返回 accepted/succeeded/failed |
| `GET /v1/moderation/queue` | 审核队列（管理员） | 需要 moderator 角色；支持 cursor 和 priority |
| `POST /v1/moderation/reviews` | 处置并写审计记录 | 管理员角色；动作不可修改 |

`POST /v1/outbox/batch` 响应示例：

```json
{
  "results": [
    { "idempotencyKey": "evt-1", "status": "succeeded", "resource": { "id": "..." } },
    { "idempotencyKey": "evt-2", "status": "failed", "error": { "code": "RATE_LIMITED", "retryable": true } }
  ]
}
```

## 5. 状态与并发规则

- Prayer/Testimony：`pending → published`（审核通过）、`pending → rejected`、`published → hidden`（举报/审核）、`hidden → published`（恢复）、任意非 deleted 状态 → `deleted`（作者删除或管理员处置）。`deleted` 不可恢复。
- Report：`open → triaged → actioned|dismissed|duplicate`；`critical` 举报需在运营 SLA 内人工确认。
- Identity：`active ↔ suspended`；用户删除后为 `deleted`，禁止重新激活原身份。
- 更新资源时优先使用 `If-Match: <version>`；版本不匹配返回 `409 VERSION_CONFLICT`，客户端重新拉取并按领域规则合并。祷告计数由服务端原子增减，不能用客户端数值覆盖。

## 6. 客户端迁移与验收清单

Phase 0 完成前，客户端 repository 以接口类型隔离远程供应商；`src/data.ts` 降为 fixture。AsyncStorage schema v2→v3 至少迁移：

1. 将 `publishedPrayers` 映射为带 `status=pending`、`source=user`、`version=1` 的本地 Prayer；
2. 将 `prayedIds` 生成 `prayer_action` outbox 事件（不重复生成已有 key）；
3. 为每个本地写入生成 `idempotencyKey` 和 `createdAt`；
4. 迁移失败时保留 v2 原文并回退为空队列，记录可观测错误。

评审验收：领域字段与状态无歧义；所有写接口具备幂等和权限说明；列表接口具备 cursor 分页；删除、举报和审核可追溯；离线事件可重试且不会重复计数；契约可由 TypeScript 类型或 OpenAPI 生成并在 CI 校验。

