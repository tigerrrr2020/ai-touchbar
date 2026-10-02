# 隐私与数据访问

本项目没有开发者服务器、遥测、广告 SDK 或远程对话上传功能。以下描述针对 0.2.1 的 App 调用路径，不代表被读取的第三方客户端或服务本身。

## 本机读取

- Codex 任务选择器只读 `~/.codex/state_5.sqlite`；查询任务 ID、名称、归档与排序字段，最多 40 条，不写数据库。
- Codex 状态解析 `~/.codex/sessions/` 下所选任务的 JSONL；额度回退也会解析 sessions / archived_sessions 中的额度事件。日志本身可能包含对话与工具输出，因此程序具有读取相应文件的能力；只提取状态／额度，不将日志内容发往开发者或提供商。
- Kimi 状态读取 `~/.kimi-code/server/instances/`、`server.token` 和 `sessions/` 的 wire 日志。仅接受唯一、近期有心跳的本地实例，将服务令牌发给 `127.0.0.1`，禁用代理与跳转，不启动新任务。
- Kimi 额度读取 `~/.kimi-code/credentials/kimi-code.json`，或旧版 `~/.kimi/credentials/kimi-code.json`；该模块支持 `KIMI_CODE_HOME` / `KIMI_SHARE_DIR`。任务状态与 Codex 列表仍使用默认目录，非默认目录并非全面支持。

## 联网与凭据写入

- Codex 额度启动一个短生命周期的 `codex app-server` 子进程，仅调用额度读取方法，认证由已登录的 Codex CLI 管理。App 不直接读取或打印 Codex token，也不调用上游保留的 `maybe_active_refresh` 模型探测函数。
- Kimi 额度请求 `https://api.kimi.com/coding/v1/usages`，使用现有 OAuth access token。
- access token 过期或被拒绝时，可能通过 `https://auth.kimi.com/api/oauth/token` 刷新。实现使用锁、重新读取和原子替换，**会写回当前或旧版的本机凭据文件**；失败时退避，不要求用户贴出 token。
- Kimi token 通过子进程标准输入传给 `curl`，不放在命令行参数中。额度请求可能遵循用户已有的代理环境变量。
- 普通启动即启用上述实时读取；不希望读取账号时，请只以 `--demo` 启动。

## 缓存与临时文件

- `~/.cache/usage-widget/`：额度快照、失败缓存、刷新退避；Kimi 月限额观察缓存也包含日志路径、文件签名与状态时间，不保存完整对话或 token。
- 系统临时目录：短期 bridge 输出、额度图像；任务正常结束时清理。临时任务列表可能包含本机任务名称；异常退出后的系统临时文件不应上传。
- App bundle 不保存账号、日志或查询缓存。没有自动更新器，也不会改 BTT、系统听写或开机启动设置。

## 测试与实际能力

README GIF 与 `--demo` 均为离线模拟。操作框中的“测试模拟”只暂停任务状态读取，普通启动下的额度查询仍继续。

离线自检使用虚构 ID、临时日志／数据库和替代接口，不调用真实模型，不读真实凭据。它能检验代码回归，不能证明每种 macOS、套餐或真实任务都兼容。

反馈问题时，只提供软件版本、硬件架构、状态类别和去敏后的错误。不要上传 `auth.json`、`credentials/`、`server.token`、SQLite 数据库、真实 JSONL 会话或未打码截图。
