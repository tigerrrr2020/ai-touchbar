# AI Touch Bar · 开发交接

更新：2026-10-23（Asia/Shanghai，0.2.6 发布后） · 源码／本机安装／发布版本：0.2.6

## 先看结论

当前是独立的 Swift / AppKit 菜单栏 App，不再依赖 BTT。本机“应用程序”已替换为 0.2.6（操作框显示版本号，仅界面改动）；被替换的旧版备份在 `~/Documents/ai-touchbar-backups/` 与 `../outputs/`。真实 Kimi 联调已在 0.2.4 上完成：自动匹配、等待审批、并发隐藏、指定任务隔离、空闲隐藏均在本机真实任务上验证；联调中发现并修复了完成状态从不触发的问题（daemon 结局字段为 `done` 而非 `success`）。服务断连恢复（10 秒保留）尚未实测。

0.2.6 已发布 **[v0.2.6 预发布版](https://github.com/tigerrrr2020/ai-touchbar/releases/tag/v0.2.6)**，包含 `AI-Touch-Bar-v0.2.6-macos-arm64.zip` 与 `SHA256SUMS.txt`，上传附件与本地 SHA-256 一致。README 下载入口已切到 0.2.6；v0.2.1、v0.2.3、v0.2.4、v0.2.5 的 tag、Release 和附件保留，0.2.2 未单独发布。后续版本发布仍按当时请求确认范围。

## 已完成

### 操作框显示版本号（0.2.6，已安装并发布）

已发布 **[v0.2.6 预发布版](https://github.com/tigerrrr2020/ai-touchbar/releases/tag/v0.2.6)**，包含 `AI-Touch-Bar-v0.2.6-macos-arm64.zip` 与 `SHA256SUMS.txt`，上传附件与本地 SHA-256 一致；README 下载入口已切到 0.2.6。

- 只在 `Sources/NativeUI.swift` 的 `setupPreview()` 增加一个只读标签：「实时概览」标题行右侧显示 `v` + `CFBundleShortVersionString`，随安装包版本自动更新，不需要手工同步文案。
- 未触碰任何读取、解析或状态逻辑；全部离线回归与自检通过，`--demo` 截图确认显示位置。

### 操作框布局重排（0.2.5，已安装并发布）

已发布 **[v0.2.5 预发布版](https://github.com/tigerrrr2020/ai-touchbar/releases/tag/v0.2.5)**，包含 `AI-Touch-Bar-v0.2.5-macos-arm64.zip` 与 `SHA256SUMS.txt`，上传附件与本地 SHA-256 一致；README 下载入口已切到 0.2.5，v0.2.1、v0.2.3、v0.2.4 的 tag、Release 和附件保留。

- 只改 `Sources/NativeUI.swift` 的窗口布局与 `Info.plist` 版本号，未触碰任何读取、解析或状态逻辑；全部离线回归与自检通过，`--demo` 截图确认布局。
- 窗口变为 640×320，只保留“实时概览”和“监看任务”两个区块。预览区改为每个模型一张黑色卡片（Codex／Kimi 并排等宽 288）：卡内上方是该模型额度、下方是状态动画；新增模型向 `providerCards` 追加一张卡片即可横向排列。
- 额度仍由 helper 输出单张 480×60 PNG（左半 Codex、右半 Kimi，`quota_touchbar.py` 固定布局），操作框在 Swift 侧裁半分卡显示；Touch Bar 继续使用整图，helper 与 Touch Bar 绘制均未改。额度不可用时两张卡片各自显示“额度未知”。
- 移除界面上的测试概念：删除“状态测试”栏、“测试模拟（48 秒）”“切回实时状态”按钮与说明文字；`--demo` 仍会在启动时自动播放一轮 48 秒模拟后回到实时，供离线检查。
- “Touch Bar 显示”栏（显示／隐藏按钮）也从操作框移除——图钉菜单已有相同入口，避免重复；菜单标题统一为“打开 TB 操作框／显示 Touch Bar／隐藏 Touch Bar”。
- 监看任务：“刷新列表”按钮与标题同一行居右（同时刷新两个列表、各自保留选择）；Codex 下拉框（x=24 宽 288）与 Kimi 下拉框（x=328 宽 288）同一行，与上方卡片等宽对齐；归属与状态说明跟在各自下拉框下方，超长截断、悬停显示全文（Codex 任务标题同理）。
- 交互、文案、选择保留逻辑全部不变；`⌘W` 关闭、图钉菜单、Touch Bar 行为未动。

### Kimi 额度恢复（0.2.2）

- 修正旧月限额事件长期覆盖当前小时／周进度条的问题，并统一秒／毫秒事件时间。
- 只有晚于限额事件的有效成功用量，或用户明确执行的本机恢复确认，才能解除旧的月限额记录；确认后出现的新月限额错误仍显示红色 `WAIT!`。
- 恢复确认写入 `~/.cache/usage-widget/kimi-monthly-recovery.json` 的时间戳，不联网、不读凭据、不创建模型任务。
- 已完成一次本机恢复确认及安装验证；不要为了测试重复操作真实确认文件。

Kimi 当前用量接口未提供月额度字段。小时／周显示有余量，不能据此推断月额度恢复；也不能凭“过了一个月”、固定 TTL 或清空缓存来判定恢复。

### Kimi 任务选择器（0.2.3）

- 自动：只监看唯一活跃任务；并发时隐藏并提示手动选择。
- 指定：按规范化 UUID 精确匹配当前服务中的任务，绝不按标题猜测或回退到另一任务。
- 不监看：停止 Kimi 状态读取、隐藏图标；额度独立运行，用户主动刷新任务列表仍会读元数据。
- 所选任务缺失时保留选择并隐藏，不从历史目录猜一个会话。选择仅在本次运行内有效，重启后 Kimi 回到自动模式，Codex 需要重选。
- 切换选择立即清除旧状态；后台与主线程回调都核对请求代次、Codex ID 和完整 Kimi 选择，过期响应不能重新点亮旧任务。
- 短暂断连只为同一监看对象保留最多 10 秒的活动状态。明确空闲、歧义、所选任务缺失、停用或身份无效立即隐藏。
- 完成需服务元数据与 wire 日志相互印证，当前短暂保留窗口为 45 秒；不能由旧完成记录覆盖一个仍在运行的任务。
- 操作框新增 Kimi 下拉框、刷新按钮和状态说明；服务未连接、未取得列表、并发、停用与所选任务缺失分开提示。

### Kimi 完成状态修复（0.2.4）

- 真实联调发现：当前 daemon 的 `agent.turn.ended` 记录结局写作 `outcome: "done"`（毫秒时间戳），解析层只认 `"success"`，完成状态与 45 秒保留窗口因此从不触发。
- `agent_status.py` 现在同时接受 `"success"` 与 `"done"`；自检补充了 `done` 结局、毫秒／秒时间、过期完成、错误结局、无 `outcome` 等离线场景。
- 真实任务链路验收通过：唯一活跃任务自动匹配、等待审批识别、双任务并发时自动模式隐藏并提示手动选择、并发下指定任务互不干扰、对方结束后自动恢复唯一活跃、空闲隐藏、指定不存在任务不回退猜测、服务在线时列表与 UI 刷新正常。

### 保持不变

- Codex 手动监看一个任务；两种提供商都不自动跟随当前对话页面。
- 像素字体、两组状态动画、额度刻度与红色 `WAIT!` 规则、图钉图标、Touch Bar 收起／恢复行为保持不变。
- `⌘W`／红色关闭按钮只关闭操作框；退出仍走图钉菜单。没有开机自启、自动更新、听写或 Siri 替换。
- 不恢复 BTT、不自动启动 Kimi 服务、不自动审批或创建任务。

## 接手代码入口

| 文件 | 关注点 |
| --- | --- |
| [NativeUI.swift](../Sources/NativeUI.swift) | 两个选择器、提示语、刷新保留选择、实时／模拟切换、窗口布局。 |
| [LiveStatusReader.swift](../Sources/LiveStatusReader.swift) | `KimiSelection`、任务列表、2 秒轮询、响应身份与代次校验、受限 helper 子进程。 |
| [AgentState.swift](../Sources/AgentState.swift) | 按监看对象隔离的 `KimiGrace`，切换与明确隐藏条件。 |
| [agent_status.py](../helper/agent_status.py) | `_kimi_live_sessions`、`_validated_kimi_sessions`、`kimi_selection_status`、wire 状态解析。 |
| [status_bridge.py](../helper/status_bridge.py) | `--kimi-tasks`、`--status --kimi-mode auto\|pinned\|off`、标题与输出限制。 |
| [quota_touchbar.py](../helper/quota_touchbar.py) | 月限额事件时序、恢复确认、额度绘制与内置回归。 |
| [test_status_bridge.py](../helper/test_status_bridge.py) / [PrototypeChecks.swift](../Sources/PrototypeChecks.swift) | 双任务、身份、过期响应、grace、UI 资源与窗口行为测试。 |

### 不要破坏的读取约束

1. 只接受一个有效、近期有心跳的本地 Kimi daemon；当前心跳窗口为 90 秒。请求限于已校验的 `127.0.0.1`，禁用代理和重定向。
2. 服务列表必须完整、无分页且最多 100 项；非法或重复身份让整批结果失效，不能先丢掉坏条目再宣布“唯一任务”。菜单最多 40 项，优先保留所选任务和活跃项。
3. 标题只从服务候选任务对应的 `state.json` 读取，文件上限 64 KiB，校验 ID 后取 `title`。不用 `lastPrompt`；去控制字符、限制长度并附短 ID。找不到可靠标题时显示短 ID。
4. bridge 标准输出上限 16 KiB。状态 JSON 同时包含选择模式、请求 ID、实际解析 ID 和原因；Swift 端继续核对身份，不能只接收状态文字。
5. 审批依据当前 daemon 的 `pending_interaction`，不能让旧 wire 审批记录覆盖当前非审批状态。
6. 额度与任务状态分开：服务断连不是额度耗尽；月限额也不是“没有运行任务”。

## 前端修改接手（给下一个会话）

本 App 没有 Web 前端，“前端”指两层原生界面，都是 Swift / AppKit，无第三方依赖：

| 层 | 文件 | 内容 |
| --- | --- | --- |
| 操作框（NSWindow） | [Sources/NativeUI.swift](../Sources/NativeUI.swift) | 实时概览文字、额度预览图、Codex/Kimi 下拉框、刷新按钮、状态说明、底部按钮排布。改布局、文案、交互从这里入手。 |
| Touch Bar | [Sources/TouchBarUI.swift](../Sources/TouchBarUI.swift)、[Sources/ControlStrip.swift](../Sources/ControlStrip.swift) | NSTouchBar 组装、收起／恢复按钮、状态图标与额度区绘制入口。 |
| 状态动画 | [Sources/StatusDemo.swift](../Sources/StatusDemo.swift)、`status-assets/` | 两组像素动画帧的加载与播放；帧由 `scripts/generate_status_assets.py`（Pillow）离线生成，不要手改 PNG。 |
| 额度绘制 | [Sources/QuotaReader.swift](../Sources/QuotaReader.swift)、[helper/quota_touchbar.py](../helper/quota_touchbar.py) | Swift 侧读缓存，Python 侧查询与绘图；示意图由 `scripts/generate_quota_previews.py` 重建。 |

修改时的约束与流程：

1. 先读根目录 `AGENTS.md`（若存在）与本文件；“不要破坏的读取约束”一节对任何改动都适用。
2. 纯界面改动不要碰 `helper/` 的读取与解析逻辑；改状态、额度或并发逻辑必须同步补离线回归（`helper/test_status_bridge.py`、`agent_status.py --self-test`）。
3. 验证命令见下节：`build.sh` + `test.sh` + `codesign --verify`；AppKit 自检需要已登录图形会话。界面改动后另用 `--demo` 做离线交互检查。
4. 版本号在 `Info.plist`（CFBundleVersion 与 CFBundleShortVersionString 同步改）；发布需单独授权，流程参考本次 v0.2.4 的 git 历史。
5. 动画节奏为 6 fps、任务状态约 2 秒轮询、额度约 10 秒刷新——保持轻量，不要引入高频定时器。

## 验证记录与边界

以下记录对应本次 0.2.3 源码和安装版，不代表所有硬件或提供商版本：

| 验证层 | 已有证据 | 尚不能证明 |
| --- | --- | --- |
| Python 回归 | 10 项状态桥接测试、44 项上游模块测试、bridge 生命周期检查、状态与额度自检通过。 | 真实 daemon 返回的数据完全符合假设。 |
| Swift 自检 | 选择／身份／代次、A→B→停用、grace、模拟数据、菜单图标、窗口关闭、Touch Bar 恢复按钮、状态帧、超时与异常 JSON 检查通过。 | 实体设备上真实任务的完整状态转换。 |
| 安装一致性 | 本机 App 版本为 0.2.6；签名校验通过，变更 helper 与源码逐字节一致。 | Developer ID 签名或 Apple 公证；当前只有 ad-hoc 签名。 |
| 发布产物 | 0.2.3 重新构建、离线测试、ZIP 完整性及解压后签名检查通过；上传附件与本地 SHA-256 一致。 | 真实 Kimi 联调、Intel 或其他系统版本的兼容性。 |
| 安装版 UI | 自动／不监看选项可见；停用隐藏状态但保留额度；刷新不重置选择；两组模拟动画布局已检查，随后切回实时模式。 | 真实任务 A／B 的下拉切换。当前服务未连接，列表中没有可用真实任务。 |
| 实体 Touch Bar | 之前已有人确认五种模拟状态、布局、空闲隐藏及图钉收起／展开正常。 | 新选择器在真实 Kimi 并发、审批、完成、服务重启时的设备表现。 |

离线测试中的虚构 A／B 任务不消耗 Kimi 额度。普通 App 的“测试模拟”只替换任务状态，额度查询仍继续；完全离线必须使用 `--demo`。

## 复现与检查命令

在仓库根目录执行。构建拒绝覆盖已有目标，请使用新的输出目录：

```sh
verification_dir="$(mktemp -d "${TMPDIR:-/tmp}/ai-touchbar-verify.XXXXXX")"
verification_app="$verification_dir/AI Touch Bar.app"
bash build.sh "$verification_app"
bash test.sh "$verification_app"
codesign --verify --deep --strict "$verification_app"
git diff --check
```

`test.sh` 不调用真实模型或读取真实凭据。AppKit 自检需要已登录的 macOS 图形会话；沙箱阻断 WindowServer 注册时可能在断言前失败，应记录环境问题，不能据此声称设备通过或代码失败。

完全离线交互检查（先从图钉菜单正常退出其他副本）：

```sh
"$verification_app/Contents/MacOS/TouchBarNativeLive" --demo
```

先选择“模拟任务 A”（命令），再选 B（改文件），再选自动（两个任务并发，隐藏），最后选不监看（隐藏）。刷新应保留选择。此交互路径已提供，双任务逻辑已自动测试；本轮没有把它当作真实任务验收。

恢复确认命令见 [README](../README.md#kimi-月额度恢复022-起)，只在用户确认月额度确实恢复时运行。不要用它当健康检查。

## 真实 Kimi 联调结果（2026-10-23，0.2.4）

已在用户授权下用真实任务完成验收（新建了一个最小会话验证并发，已完成并保留记录）：

- [x] 一个任务运行：自动模式匹配该任务；空闲后隐藏。完成短暂显示绿色依赖 0.2.4 的 `done` 结局修复，实机绿色确认以用户目测为准。
- [x] 两个真实任务同时运行：自动模式报 `ambiguous` 并提示手动选择；指定 A 后只显示 A，B 的状态变化不影响 A；B 结束后自动恢复为唯一活跃的 A。
- [x] 快速 A→B→不监看：桥接层逐次核对身份，旧响应不点亮旧任务；刷新列表不换选择，额度仍显示。
- [x] 指定不存在的任务：返回缺失原因，不回退到其他任务。
- [x] 等待审批／用户输入：由当前服务元数据触发，已实测两轮。
- [ ] 服务断连与恢复：同一任务的活动状态最多保留 10 秒；超时隐藏；恢复后读取当前任务，不重用另一会话。（未实测，需要重启 daemon，未在用户环境执行）
- [x] 实体 Touch Bar：用户确认运行中图标与额度条显示正常。

补充观察：`kimi -p` 启动的 CLI 会话会进入任务列表，但 daemon 不把它标记为活跃，不参与自动模式判断。

如果数据格式不同，先在本机检查字段与类型，去敏后补离线 fixture 和回归，再修改解析。不要猜字段、抓取完整对话、改用最新日志兜底或让动画常驻来掩盖识别失败。

## 已排除的错误路线与发布边界

- 不恢复“唯一活跃任务”作为手动模式的限制；多任务时应按用户固定的 ID 监看。
- 不用历史日志／标题猜当前页面，不把额度恢复等同于 daemon 已在线。
- 不把列表失败永久显示为服务断连；后续有效状态需能更新提示。
- 不让旧 wire 审批或旧异步回调覆盖当前状态。
- 不把单元测试、动画 GIF、界面截图写成真实任务已验收。
- 不提交真实任务名称、ID、日志、数据库、token、凭据、缓存、运行截图或本机绝对工作路径；README 现有 GIF／额度图片均为示例。
- 本次追加授权覆盖 0.2.3 的打包、GitHub 发布和 README 下载链接更新，不包含系统设置变更或创建实际模型任务。后续版本发布仍按当时请求确认范围。

继续开发前先看 `git status`，保留无关改动。复用同一代码版本的有效测试结果；修改状态、额度或并发逻辑后，补回归并重新验证受影响的路径。
