# 祷告地球 Prayer Earth

面向全球的跨平台祷告与见证应用，基于 Expo 57、React Native、Expo Router 和 TypeScript，一套代码支持 iOS、Android 与 Web。当前版本为 `1.1.0`。

当前状态复盘与后续升级计划见 [ROADMAP_UPGRADE.md](./ROADMAP_UPGRADE.md)。

## 本地运行

```bash
npm install
npm run start
```

按 `a` 打开 Android，按 `i` 打开 iOS（需要 macOS/Xcode），按 `w` 打开 Web。

### 环境变量

复制 `.env.example` 为 `.env` 后按目标环境填写。Expo 会把 `EXPO_PUBLIC_*` 变量编译进客户端，因此这里只能放公开配置；数据库密钥、JWT 签名密钥和管理令牌等服务端密钥必须放在后端或 CI 的 Secret 中。当前客户端仍可在不配置 API 地址时以离线模式运行。

GitHub Actions 的 CI 会在 Node.js 24 和 Python 3.14 上执行 TypeScript、ESLint、Vitest、后台与阅读器回归测试、Expo Doctor 和 Web 导出；提交 PR 或推送到 `main` / `master` 时自动触发。

电脑版微信群图片按方案 A 导入：另存为到仓库同级的 `WeChatImages`，再入库。步骤见 [`docs/content-import.md`](./docs/content-import.md)。

## 已实现

- Expo Router 原生 Tab、发布页、详情深链与返回栈
- FlatList 虚拟化的全球祷告、分类筛选和每日见证
- 纯 reducer + 版本化 AsyncStorage + 串行持久化队列
- “我来祷告”和用户发布内容跨重启保留
- 动态日期/相对时间、分钟刷新和前台恢复校时
- expo-image 内存/磁盘缓存、图片失败占位和空状态
- 错误边界、安全区、键盘避让和基础无障碍支持
- 社区守则、隐私说明与发布前确认
- 全新十字架品牌图标、Android adaptive icon 和启动页

## 架构

```text
app/                    Expo Router 页面与深链
  (tabs)/               首页、祷告、见证、我的
  prayer/[id].tsx       可分享的祷告详情
  compose.tsx           发布流程
  legal/                隐私与社区守则
src/
  domain/               稳定领域类型
  state/                可测试的纯 reducer
  services/             版本化本地存储边界
  repositories/         可替换的本地/远程数据访问边界
  hooks/                状态仓库与时间同步
  context/              跨路由状态生命周期
  components/           记忆化 UI 组件
  screens/              虚拟化页面实现
```

线上 MVP 的领域模型、状态流转、分页、幂等、审核和离线 outbox 契约见 [`docs/API_CONTRACT.md`](./docs/API_CONTRACT.md)。

HTTP 适配器位于 `src/repositories/httpPrayerRepository.ts`，匿名身份与本地会话位于 `src/services/identityHttp.ts` 和 `src/services/identityStorage.ts`。启动时会在远程开关开启且配置 API 地址后执行匿名身份恢复、首屏拉取和 Outbox drain；失败时保留本地快照并继续离线使用。未配置远程环境时保持离线模式。

## 质量检查

```bash
npm run verify
npm run build:web
```

`verify` 会依次执行 TypeScript、ESLint、Vitest 和 Expo Doctor。

## 上线前必须接入

当前内容与用户发布内容保存在本机，尚未连接全球生产后端。正式公开发布前需要：

- 接入 Supabase/Firebase 或自有 API，并实现 cursor 分页与离线 outbox
- 内容审核、举报、屏蔽用户和审核证据链
- 用真实运营方邮箱、网址替换隐私页中的联系占位说明
- 账号与匿名模式、数据删除入口、多语言 CMS 和推送通知
- 确认所有见证文字与图片的授权，不把图库照片描述为真实当事人
- 完成 Apple/Google 隐私问卷、UGC 政策和真机无障碍测试

## 构建商店包

```bash
npx eas-cli@22.2.0 login
npx eas-cli@22.2.0 init
npx eas-cli build --platform android --profile production
npx eas-cli build --platform ios --profile production
```

首次提交前，请把 `app.json` 中的 `org.prayerearth.app` 替换为你拥有的唯一 Bundle ID / Package Name，并通过 `eas init` 写入你的 `extra.eas.projectId`。这些标识发布后不能随意更换。
