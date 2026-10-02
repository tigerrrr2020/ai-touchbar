# Third-party notices

## AI Agent Usage Widget

部分 Touch Bar 系统桥接与额度读取代码来自：

- 项目：[lazyfoxy33-dev/ai-agent-usage-widget](https://github.com/lazyfoxy33-dev/ai-agent-usage-widget)
- 基准提交：`15dd9ff0bbe8ecdeae00e2d9ec2dd23e0dad8d81`
- 许可证：MIT，Copyright (c) 2026 AI Agent Usage Widget contributors
- 原许可证完整保留于 [UPSTREAM-LICENSE](UPSTREAM-LICENSE) 和 [helper/vendor/LICENSE](helper/vendor/LICENSE)。

对应文件：

- `Sources/ControlStrip.swift`：改编自上游 Touch Bar 的系统托盘和模态栏桥接。
- `helper/vendor/usage/{__init__,cache,codex,kimi,config,refresh_backoff}.py`：限定为本项目使用的数据读取模块。
- `helper/vendor/tests/`：上游的 Kimi、缓存、配置、刷新退避测试及 Kimi 虚构额度样例，沿用同一 MIT 许可证。
- `codex.py` 有本地修改：按实际窗口时长匹配 5 小时／周限额、允许单窗口、校验数值，并优先读取 Codex 限额分组。保留的上游主动模型探测函数不由本 App 调用。

## 图形资源与名称

CODEX / KIMI 像素状态帧由本项目的 [生成脚本](scripts/generate_status_assets.py) 绘制，README 中的 GIF 是这些帧的离线演示，不是任务执行录像。应用图标根据维护者提供的字标方向使用 AI 辅助生成；菜单栏图钉使用维护者提供的 SVG。

资源生成脚本可选使用 Pillow；Pillow 不随 App 分发，也不是运行依赖。脚本生成联系表时使用系统字体，不分发字体文件。

Apple、Touch Bar、Codex、OpenAI、Kimi 等名称属于各自权利人。本项目是独立社区工具，不代表任何厂商，也不暗示官方合作或背书。
