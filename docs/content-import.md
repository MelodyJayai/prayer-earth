# 同工内容试用版导入

## 方案 A：电脑版微信「另存为」

每天在电脑版微信里把群图片「另存为」到一个平铺目录，文件名保持微信默认的 `Weixin Image_YYYYMMDD….jpg`（脚本靠文件名里的 8 位日期归类）。这些原图放在仓库外面。

本机目录与检出目录 `J:\研发\GitHub\prayer-earth` 同级：

`J:\研发\GitHub\WeChatImages`

脚本按下面顺序选用目录：

1. 命令行 `--source`
2. 环境变量 `PRAYER_WECHAT_IMAGES`
3. 旧路径 `<仓库>/WeChatImages/WeChatImages`（这个目录存在时优先，原来的导入方式可以继续用）
4. 同级目录 `<仓库>/../WeChatImages`（对应 `J:\研发\GitHub\WeChatImages`）

`--source` 或 `PRAYER_WECHAT_IMAGES` 指向的路径不存在时，脚本报错并停止。两个默认目录都不存在时同样报错，并在报错里写出试过的路径。

仓库里如果还留着 `WeChatImages/WeChatImages`（哪怕是空目录或 junction），第 3 步会命中它，同级目录不会被读取。只用同级目录时，移走仓库内的这个目录。

### 每天怎么做

1. 电脑版微信打开图片，选「另存为」，保存到 `J:\研发\GitHub\WeChatImages`。
2. 在仓库目录先核对来源，再导入。导入按 SHA-256 去重，同一批图片可以重复执行。
3. 重新启动或导出 Expo 试用包。

在 `J:\研发\GitHub\prayer-earth` 打开 PowerShell：

```powershell
cd J:\研发\GitHub\prayer-earth
python scripts/import-wechat-content.py --dry-run
python scripts/import-wechat-content.py
```

`--dry-run` 只打印解析到的目录和顶层 `.jpg` 文件名，不写 `assets/content/`、`docs/content-import-manifest.json`、`src/contentData.ts`。核对输出里的 `source=` 应是 `J:\研发\GitHub\WeChatImages`。

要写明路径时：

```powershell
python scripts/import-wechat-content.py --dry-run --source "J:\研发\GitHub\WeChatImages"
python scripts/import-wechat-content.py --source "J:\研发\GitHub\WeChatImages"
```

当前 PowerShell 窗口也可以先设环境变量：

```powershell
$env:PRAYER_WECHAT_IMAGES = "J:\研发\GitHub\WeChatImages"
python scripts/import-wechat-content.py --dry-run
python scripts/import-wechat-content.py
```

若提示找不到 `python`，把命令里的 `python` 换成 `py -3`。同一时间只跑一个导入：脚本会先清掉已生成的试用图片再整批重写。

### 监视新图片

`scripts/watch-wechat-images.ps1` 轮询来源目录里的顶层 `.jpg`。文件名、大小、修改时间连续约 3 秒不变后，调用上面的导入脚本，并把 `--source` 设成正在监视的那个目录。来源目录里一张 `.jpg` 都没有时，监视脚本不调用导入。日志写在 `.wechat-import/watch.log`（已 gitignore，超过约 2MB 会轮转）。

已经在目录里的图片先导入一次，再开监视：

```powershell
cd J:\研发\GitHub\prayer-earth
python scripts/import-wechat-content.py --source "J:\研发\GitHub\WeChatImages"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\watch-wechat-images.ps1 -Source "J:\研发\GitHub\WeChatImages"
```

监视停在前台，直到 Ctrl+C。启动前就已经在目录里的文件不会再次触发导入；要在启动时把它们纳入试用库，加上 `-ImportOnStart`。调整稳定等待时间用 `-DebounceSeconds 5`（最少 1 秒）。

登录后在后台挂着：把下面整段贴到当前 PowerShell 窗口执行一次。CI 和仓库不会替你创建这个任务。

```powershell
$repo = "J:\研发\GitHub\prayer-earth"
$watch = Join-Path $repo "scripts\watch-wechat-images.ps1"
$action = New-ScheduledTaskAction `
    -Execute "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watch`" -ImportOnStart" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "Prayer-WeChat-Image-Watch" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Import WeChat Save As images into the prayer-earth trial library."
```

`-ImportOnStart` 会在任务启动时立刻全量导入。执行前先用 `--dry-run` 确认来源是 `J:\研发\GitHub\WeChatImages`。任务按默认设置在当前用户登录后运行，这样能访问你平时使用的 `J:` 盘。任务计划程序里看 `Prayer-WeChat-Image-Watch`；输出在 `J:\研发\GitHub\prayer-earth\.wechat-import\watch.log`。

不想留常驻进程时，用计划任务按间隔直接跑同一条导入命令，去重规则相同：

```powershell
python scripts/import-wechat-content.py --source "J:\研发\GitHub\WeChatImages"
```

`.gitignore` 忽略仓库内任意名为 `WeChatImages` 的目录（含 junction 和旧的嵌套目录）。同级的 `J:\研发\GitHub\WeChatImages` 在仓库外面。

## 当前导入结果

- 晨修：122 条
- 宣教动态与见证：89 条
- 跳过重复文件：3 张
- 跳过非内容节日祝福图：1 张

导入脚本会按文件名中的日期识别内容，并按图片长度/颜色密度将内容分到两个栏目；对已确认的栏目例外会使用脚本中的人工覆盖表并记录原因。本批次有 1 张“MS 解经／马可福音逐节查经”图片人工归入晨修。脚本目前用“可解码且达到最低尺寸”作为技术筛选，并不能单独证明图片没有模糊或内容截断；需要人工复核的图片应在清单外另行标注。超过 4096 像素高度的长图会切成连续片段，应用详情页按原顺序拼接显示，避免移动设备纹理尺寸过大。脚本不会修改微信原始图片。

每条已导入内容都会记录源文件 SHA-256。重新导入时，清单中已经存在的 `sourceFile` 会继续使用原来的 ID；新文件使用“栏目-日期-SHA-256 前 12 位”生成稳定 ID，因此补录早期图片不会让旧详情链接整体变化。清单的 `skipped` 字段记录重复、无法读取、已知排除或低于最低尺寸门槛的文件及原因，便于每日增量核对。

以后微信群新增图片后，按上面的方案 A 放进来源目录再导入，然后重新启动或导出 Expo 试用包。生成的数据清单在 `docs/content-import-manifest.json`，应用索引在 `src/contentData.ts`，图片资源在 `assets/content/`。

试用版内容页入口仍使用底部的“晨修·宣教”标签，页面内可切换“晨修”“宣教动态与见证”，也可按月份和日期搜索。点击卡片可打开完整原图。

导入内容保持微信群图片原貌，当前没有把图片自动转写成文字，也没有将其标记为“已核实见证”。
