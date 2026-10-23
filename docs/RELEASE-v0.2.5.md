# AI Touch Bar 0.2.5

也许，现在才是 Touch Bar 的「最佳赏味期限」。

本次为操作框界面重排，只改窗口布局，不触碰任何状态、额度或并发读取逻辑。

## 更新内容

- **实时概览按模型分卡**：Codex、Kimi 各一张卡片并排显示，卡内上方是该模型的额度条、下方是状态动画；后续新增模型可以直接加一张卡片。
- **监看任务更紧凑**：Codex 与 Kimi 下拉框合并为一行并与卡片等宽对齐，归属与状态说明跟在各自下拉框下方，超长截断、悬停显示全文；「刷新列表」按钮移到标题行，一次刷新两个列表并各自保留选择。
- **移除重复与测试入口**：操作框不再放「显示／隐藏 Touch Bar」（图钉菜单已有相同入口），测试模拟按钮从界面移除（`--demo` 离线检查保留）；菜单标题统一为「打开 TB 操作框／显示 Touch Bar／隐藏 Touch Bar」。
- 窗口缩小到 640×320；Touch Bar 显示、像素动画、额度规则、`⌘W` 关闭与图钉菜单行为均不变。

## 下载与安装

下载本页附件：

- `AI-Touch-Bar-v0.2.5-macos-arm64.zip`
- `SHA256SUMS.txt`

将两者放在同一目录，核对下载完整性：

```sh
shasum -a 256 -c SHA256SUMS.txt
```

升级前，从菜单栏图钉选择“退出”旧版。解压后，将 `AI Touch Bar.app` 拖入“应用程序”；打开操作框后点击“显示 Touch Bar”。无需退出 Codex 或 Kimi，也不会停止它们的任务。重启后 Codex 需要重新选择监看任务，Kimi 回到自动模式。

安装包仅支持 **Apple Silicon（arm64）**，构建目标 macOS 13+，验证环境为 macOS 15.8。需要可运行的 `/usr/bin/python3`（Python 3.9+）及系统 `curl`；未捆绑 Python 运行时。Intel 用户可从源码构建，尚未实机验证。

**实验性预发布版，仅 ad-hoc 签名，未经过 Apple Developer ID 签名或公证。** 首次打开的安全提示见 [README](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.5/README.md#下载与使用)。请核对来源与校验值，不要关闭系统全局安全检查。

## 验证与已知限制

发布构建已通过 10 项状态桥接测试、44 项上游模块测试、bridge 生命周期检查、状态／额度自检、原生 AppKit 自检、签名及 ZIP 完整性检查。离线样例不调用真实模型或读取真实凭据。新版界面已通过 `--demo` 离线交互检查，并已在本机安装运行。

真实 Kimi 联调在 0.2.4 上完成（自动匹配、并发隐藏、指定任务隔离、审批识别、空闲隐藏），0.2.5 未改动相关逻辑。服务断连恢复（10 秒保留）未实测。Codex 仍需手动选择任务，不会自动跟随当前页面。

Touch Bar 桥接使用私有系统接口，兼容性可能随 macOS 改变。没有开机自启、听写、Siri 替换或自动审批。

实时额度会读取本机已登录客户端；Kimi OAuth 可能刷新并写回本机凭据。完整边界见 [隐私说明](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.5/docs/PRIVACY.md)与 [开发交接](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.5/docs/HANDOFF.md)。本次保留 v0.2.1、v0.2.3 与 v0.2.4 发布及附件，不覆盖旧包。
