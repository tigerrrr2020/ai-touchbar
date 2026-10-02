# AI Touch Bar 0.2.1

也许，现在才是 Touch Bar 的「最佳赏味期限」。

首个整理后的开源发布：原生 macOS 菜单栏 App，无需 BetterTouchTool。

- Codex / Kimi 额度进度条、30% / 50% 刻度、耗尽 `WAIT!` 状态。
- CODEX 的 O 动画与 KIMI 的 i 点动画，README 含 GIF 演示。
- Codex 手动选择任务；Kimi 唯一活动任务识别。
- 菜单栏图钉、操作框、收起后点击图钉恢复；关闭操作框不退出 App。
- 独立构建源码、离线检查、MIT 与上游版权声明。

## 下载

`AI-Touch-Bar-v0.2.1-macos-arm64.zip`：解压后把 `AI Touch Bar.app` 拖入“应用程序”。升级前从图钉菜单退出旧版。`SHA256SUMS.txt` 用于核对下载完整性。

此包只支持 Apple Silicon，构建目标 macOS 13+，实测环境 macOS 15.8；需要可用的 `/usr/bin/python3`（3.9+）。Intel 用户可从源码编译，尚未实机验证。

发布前已通过两个桥接测试、44 项上游单元测试、状态／额度解析自检、原生 App 自检及签名完整性检查。状态帧和 README GIF 已核对；发布源码不含本机凭据、会话数据库或运行日志。

**实验性版本，仅 ad-hoc 签名，未经过 Apple Developer ID 签名或公证。** 首次安装安全提示见 [README](https://github.com/tigerrrr2020/ai-touchbar#下载与使用)；不要关闭系统全局安全检查。

## 已知限制

Codex 不会自动跟随当前页面，审批状态识别仍不完整。Kimi 真正运行／审批的完整流程仍待实测；GIF 与 48 秒模拟不是实测录像。Touch Bar 桥接使用私有系统接口，兼容性可能随 macOS 改变。无开机自启、听写或自动审批。

实时额度会读取本机已登录客户端，Kimi OAuth 可能刷新并写回本机凭据。详见 [隐私说明](https://github.com/tigerrrr2020/ai-touchbar/blob/main/docs/PRIVACY.md)。
