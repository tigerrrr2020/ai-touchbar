# AI Touch Bar 0.2.8

也许，现在才是 Touch Bar 的「最佳赏味期限」。

本次只更新图标：App 图标沿用菜单栏图钉，把左下针体做成绿/青额度刻度，不再单独绘制进度条。没有改动任务状态、额度读取或解析逻辑。

## 更新内容

- **App 图标**：白色图钉主体，左下针体填绿/青渐变并加刻度线；颜色只存在于针体，不再单独放一条进度条。
- **菜单栏图钉**：保留原造型，仅扩大 SVG viewBox 留白，18px 下更接近系统图标的比例；浅色／深色菜单栏自动反色。
- **无功能改动**：任务选择、状态识别、额度读取和解析逻辑与 0.2.7 相同；版本号更新为 0.2.8。

## 下载与安装

下载本页附件：

- `AI-Touch-Bar-v0.2.8-macos-arm64.zip`
- `SHA256SUMS.txt`

将两者放在同一目录，核对下载完整性：

```sh
shasum -a 256 -c SHA256SUMS.txt
```

升级前，从菜单栏图钉选择“退出”旧版。解压后，将 `AI Touch Bar.app` 拖入“应用程序”；打开操作框后点击“显示 Touch Bar”。无需退出 Codex 或 Kimi，也不会停止它们的任务。重启后 Codex 需要重新选择监看任务，Kimi 回到自动模式。

安装包仅支持 **Apple Silicon（arm64）**，构建目标 macOS 13+，验证环境为 macOS 15.8。需要可运行的 `/usr/bin/python3`（Python 3.9+）及系统 `curl`；未捆绑 Python 运行时。Intel 用户可从源码构建，尚未实机验证。

**实验性预发布版，仅 ad-hoc 签名，未经过 Apple Developer ID 签名或公证。** 首次打开的安全提示见 [README](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.8/README.md#下载与使用)。请核对来源与校验值，不要关闭系统全局安全检查。

## 验证与已知限制

发布构建已通过 10 项状态桥接测试、44 项上游模块测试、bridge 生命周期检查、状态／额度自检、原生 AppKit 自检（含菜单图标加载）、签名及 ZIP 完整性检查。图标资源与版本号之外没有代码改动；离线样例不调用真实模型或读取真实凭据。

真实 Kimi 联调已在 0.2.4 完成：自动匹配、并发隐藏、指定任务隔离、审批识别、空闲隐藏均通过；服务断连恢复（10 秒保留）未实测。Codex 仍需手动选择任务，不会自动跟随当前页面，真实审批状态识别尚不完整。

Touch Bar 桥接使用私有系统接口，兼容性可能随 macOS 改变。没有开机自启、听写、Siri 替换或自动审批。

实时额度会读取本机已登录客户端；Kimi OAuth 可能刷新并写回本机凭据。完整边界见 [隐私说明](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.8/docs/PRIVACY.md)与 [开发交接](https://github.com/tigerrrr2020/ai-touchbar/blob/v0.2.8/docs/HANDOFF.md)。本次保留 v0.2.1、v0.2.3–v0.2.7 发布及附件，不覆盖旧包。
