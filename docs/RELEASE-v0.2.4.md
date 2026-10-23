# AI Touch Bar 0.2.4

也许，现在才是 Touch Bar 的「最佳赏味期限」。

本次更新修复 Kimi 任务完成后 Touch Bar 不显示绿色「完成」的问题：当前版本的本地服务把回合结局写作 `done`，而旧版解析只认 `success`，导致完成状态与 45 秒保留窗口从不触发。

## 更新内容

- **修复 Kimi 完成状态识别**：同时接受 `success` 与 `done` 两种结局字段，兼容秒／毫秒事件时间。修复后任务成功结束时，KIMI 会短暂变绿再收起。
- **真实任务链路已验收**：自动匹配唯一活跃任务、双任务并发时提示手动选择、指定任务互不干扰、等待审批识别、空闲隐藏、指定不存在任务不回退猜测，均已在本机真实任务上验证。
- 已知边界：`kimi -p` 启动的 CLI 会话会出现在任务列表中，但不参与自动模式的活跃判断；服务断连恢复（10 秒保留）尚未实测。

## 下载与安装

下载本页附件：

- `AI-Touch-Bar-v0.2.4-macos-arm64.zip`
- `SHA256SUMS.txt`

将两者放在同一目录，核对下载完整性：

```sh
shasum -a 256 -c SHA256SUMS.txt
```

升级前，从菜单栏图钉选择“退出”旧版。解压后，将 `AI Touch Bar.app` 拖入“应用程序”；打开操作框后点击“显示 Touch Bar”。无需退出 Codex 或 Kimi，也不会停止它们的任务。重启后 Codex 需要重新选择监看任务，Kimi 回到自动模式。

安装包仅支持 **Apple Silicon（arm64）**，构建目标 macOS 13+，验证环境为 macOS 15.8。需要可运行的 `/usr/bin/python3`（Python 3.9+）及系统 `curl`；未捆绑 Python 运行时。Intel 用户可从源码构建，尚未实机验证。

**实验性预发布版，仅 ad-hoc 签名，未经过 Apple Developer ID 签名或公证。** 首次打开的安全提示见 [README](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.4/README.md#下载与使用)。请核对来源与校验值，不要关闭系统全局安全检查。

## 验证与已知限制

发布构建已通过 10 项状态桥接测试、44 项上游模块测试、bridge 生命周期检查、状态／额度自检、原生 AppKit 自检、签名及 ZIP 完整性检查。离线样例不调用真实模型或读取真实凭据。

真实 Kimi 联调已在本机完成：自动匹配、并发隐藏、指定任务隔离、审批识别、空闲隐藏均通过；完成状态解析用真实 wire 记录验证。服务断连恢复（10 秒保留）未实测。Codex 仍需手动选择任务，不会自动跟随当前页面，真实审批状态识别尚不完整。

Touch Bar 桥接使用私有系统接口，兼容性可能随 macOS 改变。没有开机自启、听写、Siri 替换或自动审批。

实时额度会读取本机已登录客户端；Kimi OAuth 可能刷新并写回本机凭据。完整边界见 [隐私说明](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.4/docs/PRIVACY.md)与 [开发交接](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.4/docs/HANDOFF.md)。本次保留 v0.2.1 与 v0.2.3 发布及附件，不覆盖旧包。
