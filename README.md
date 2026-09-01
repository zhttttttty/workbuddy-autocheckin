# WorkBuddy AutoCheckin

WorkBuddy 每日积分自动签到脚本，面向青龙面板，也可以直接在 Linux、macOS 和 Windows 上运行。

项目以稳定签到为重点：支持多账号、重复运行、JWT 自动解析 UID、Token 到期提醒、积分余额、请求重试及青龙通知。脚本仅使用 Python 标准库，不需要安装 `requests`。

> 本项目是非官方个人自动化工具。接口可能随 WorkBuddy 更新而变化，请只用于本人账号，并自行评估账号规则与使用风险。

## 功能

- 调用腾讯 WorkBuddy 官方接口完成每日签到。
- 先查询签到状态，未签到时才领取；服务端返回 `code=10001` 时按“今日已签到”处理。
- 状态接口出现 `404/405` 时自动尝试兼容路径。
- 使用一个 `WORKBUDDY_ACCOUNTS` JSON 数组配置单账号或多账号。
- UID 自动从 JWT 解析，无需单独配置。
- 识别 HTTP `401/403` 登录态失效。
- 网络错误、`429` 和常见 `5xx` 状态自动重试。
- 多账号之间加入随机间隔，避免同一时刻连续请求。
- 可显示本次积分、连续签到天数、连签奖励日和当前积分余额。
- Token 到期前预警。
- 支持青龙 `notify.py` 和 PushPlus 通知。
- 默认锁定 `https://copilot.tencent.com`，不允许通过环境变量更换接口域名。

## 文件结构

```text
workbuddy-autocheckin/
├── workbuddy_signin.py
├── tests/
│   └── test_workbuddy_signin.py
├── README.md
├── LICENSE
└── .gitignore
```

## 获取 Token

Token 保存在 WorkBuddy 桌面端的登录态文件中，不需要抓包，也不需要打开开发者工具。

### 第一步：登录 WorkBuddy

打开 WorkBuddy 桌面端并正常登录。确认客户端已经进入主界面后，再查找下面的登录态文件：

| 系统 | 新版登录态文件 |
|---|---|
| Windows | `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` |
| Windows 回退 | `%APPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` |
| macOS | `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` |
| Linux | `~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` |

Windows 用户可以按 `Win + R`，粘贴下面的路径并回车：

```text
%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth
```

如果该目录不存在，再尝试：

```text
%APPDATA%\CodeBuddyExtension\Data\Public\auth
```

macOS 用户可以在 Finder 中按 `Command + Shift + G`，粘贴表格中的 macOS 路径。

### 第二步：复制 accessToken

使用记事本、VS Code 或其他文本编辑器打开 `workbuddy-desktop.info`。文件内容是 JSON，结构大致如下：

```json
{
  "auth": {
    "accessToken": "eyJhbGciOi...这里是很长的完整Token"
  }
}
```

找到 `auth` 对象中的 `accessToken`，只复制双引号里面的完整内容：

```text
eyJhbGciOi...这里是很长的完整Token
```

复制时注意：

- 不要复制两侧的双引号。
- 不要复制 `"accessToken":`。
- 不要在 Token 前添加 `Bearer `。
- 不要截断 Token，也不要把文档示例中的 `...` 当作 Token 的一部分。
- UID 会由脚本自动解析，不需要复制 `uid` 或配置其他账号 ID。

### 第三步：写入环境变量

将复制出的 Token 填入 `WORKBUDDY_ACCOUNTS` JSON。单账号示例：

```json
[{"name":"我的账号","token":"粘贴刚才复制的完整Token"}]
```

多账号时，分别登录每个账号并复制 Token。切换账号前先保存当前 Token，因为登录态文件可能会被新账号覆盖：

```json
[{"name":"账号一","token":"第一个完整Token"},{"name":"账号二","token":"第二个完整Token"}]
```

如果没有找到登录态文件，请确认 WorkBuddy 桌面端已完成登录并进入主界面，然后重启客户端再检查上述两个 Windows 路径。不同客户端版本的存储路径可能变化，也可以在用户目录中搜索文件名 `workbuddy-desktop.info`。

Token 等同于账号登录凭据，请勿发到群聊、Issue、公开仓库或截图中。

## 青龙面板部署

### 方式一：订阅仓库

在青龙面板的“订阅管理”中新建订阅：

```text
https://github.com/zhttttttty/workbuddy-autocheckin.git
```

订阅规则保留：

```text
workbuddy_signin.py
```

不同青龙版本的订阅界面可能略有差异。如果订阅没有生成脚本，可以使用下面的手动方式。

### 方式二：手动添加

1. 打开仓库中的 `workbuddy_signin.py`。
2. 在青龙“脚本管理”中新建同名文件并粘贴内容。
3. 在“环境变量”中添加 Token。
4. 在“定时任务”中新建任务：

```bash
task workbuddy_signin.py
```

推荐 Cron：

```cron
7 1,9,17 * * *
```

脚本具备幂等处理，一天运行多次不会重复领取。请确认青龙面板时区符合你的预期。

## 环境变量

### 必填变量：`WORKBUDDY_ACCOUNTS`

脚本只读取 JSON 格式的 `WORKBUDDY_ACCOUNTS`，不再支持旧版
`WORKBUDDY_TOKEN`、`名称#Token` 或 `Token1&Token2` 格式。

JSON 的整体结构是一个数组，数组中的每个对象代表一个 WorkBuddy 账号：

```json
[
  {
    "name": "账号名称",
    "token": "完整accessToken"
  }
]
```

字段说明：

| 字段 | 是否必填 | 类型 | 说明 |
|---|---|---|---|
| `name` | 否 | 字符串 | 日志和通知中显示的名称；省略时显示脱敏 UID 或 `账号N` |
| `token` | 是 | 字符串 | 从登录态文件中复制的完整 `auth.accessToken` |

### 青龙面板填写方法

进入青龙面板 → **环境变量** → **新建变量**，分别填写：

| 青龙输入框 | 填写内容 |
|---|---|
| 名称 | `WORKBUDDY_ACCOUNTS` |
| 值 | JSON 数组，参考下面的单账号或多账号示例 |
| 备注 | 可以留空，脚本不会读取青龙备注 |

青龙面板的“名称”和“值”是两个输入框，因此不要把
`WORKBUDDY_ACCOUNTS=` 一起填进“值”输入框。

### 单账号示例

假设日志名称希望显示为“小明”，取得的完整 Token 为
`eyJhbGciOiJIUzI1NiJ9.abc123.signature`，在青龙中填写：

```text
名称：WORKBUDDY_ACCOUNTS
值：[{"name":"小明","token":"eyJhbGciOiJIUzI1NiJ9.abc123.signature"}]
备注：可留空
```

脚本日志会显示：

```text
▶ [小明]
  ✅ 签到成功
```

如果不需要自定义名称，可以省略 `name`：

```text
名称：WORKBUDDY_ACCOUNTS
值：[{"token":"你的完整Token"}]
```

### 多账号示例

多个账号写在同一个 JSON 数组中，每个 `{...}` 账号对象之间使用逗号分隔：

```json
[
  {
    "name": "小明",
    "token": "第一个账号的完整Token"
  },
  {
    "name": "小红",
    "token": "第二个账号的完整Token"
  },
  {
    "name": "小刚",
    "token": "第三个账号的完整Token"
  }
]
```

为了方便粘贴到青龙环境变量，可以压缩成一行：

```text
名称：WORKBUDDY_ACCOUNTS
值：[{"name":"小明","token":"Token1"},{"name":"小红","token":"Token2"},{"name":"小刚","token":"Token3"}]
```

这里的 `Token1`、`Token2`、`Token3` 只是位置示意，实际使用时必须分别替换为每个账号的完整 Token。

脚本会按数组顺序依次处理账号：

```text
▶ [小明]
  ✅ 签到成功

▶ [小红]
  ✅ 今日已签到

▶ [小刚]
  ❌ 登录态失效，请更新 Token
```

### JSON 填写规则

- 最外层必须是数组 `[...]`，每个账号写成 `{"name":"名称","token":"完整Token"}`。
- `token` 必填，`name` 可省略；字段和内容必须使用英文双引号，末尾不要添加逗号。
- Token 不要添加 `Bearer `，也不能使用省略号或截断内容。
- 旧版 `名称#Token&名称#Token` 格式不再支持。

配置错误时，日志会提示 JSON 出错位置或缺少 Token 的账号序号。

UID、重试次数、超时时间、积分余额查询、Token 到期提醒和多账号间隔均由脚本自动处理，不需要另外配置。

### PushPlus（可选）

如需 PushPlus 通知，再新建一个独立环境变量：

```text
名称：PUSHPLUS_TOKEN
值：你的完整 PushPlus Token
备注：可留空
```

不使用 PushPlus 时不需要创建此变量。青龙面板已有的 `notify.py` 通知渠道也不需要重复配置。

## 本地运行

Linux/macOS：

```bash
export WORKBUDDY_ACCOUNTS='[{"name":"张三","token":"你的完整Token"}]'
python3 workbuddy_signin.py
```

Windows PowerShell：

```powershell
$env:WORKBUDDY_ACCOUNTS = '[{"name":"张三","token":"你的完整Token"}]'
python .\workbuddy_signin.py
```

## 通知说明

在青龙环境中，脚本会尝试导入面板提供的 `notify.py`：

```python
from notify import send
```

如果配置了 `PUSHPLUS_TOKEN`，还会通过 HTTPS 调用 PushPlus。通知内容只包含签到结果、积分与脱敏账号标识，不包含 WorkBuddy Token。

如同时在青龙 `notify.py` 和脚本中配置同一个 PushPlus 渠道，可能收到重复通知；这种情况下只保留其中一处配置即可。

## 常见问题

### 1. 返回 401 或 403

Token 已失效或账号登录态被刷新。重新打开并登录 WorkBuddy，从登录态文件复制新的 `auth.accessToken`。

### 2. 提示 Token 中没有 UID

这只是提示，不是失败。脚本会仅使用 Bearer Token 继续请求，无需增加其他环境变量。

### 3. 状态显示未签到，但领取接口提示已签到

部分版本的状态字段可能更新不及时。脚本以领取接口返回的 `code=10001` 作为幂等兜底，会正确记录为“今日已签到”。

### 4. 查询余额失败是否影响签到

不影响。余额查询属于附加功能，失败后主签到结果仍然有效。

### 5. 为什么不支持自定义 API 地址

Token 属于高敏感凭据。为降低配置错误或恶意修改导致的泄露风险，签到接口固定为腾讯官方域名，不提供自定义地址配置。

## 测试

项目测试不访问真实 WorkBuddy 接口：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：

- 单账号与多账号 JSON 配置解析
- 账号名称显示及名称缺省回退
- 无效 JSON 和缺失 Token 的配置错误提示
- JWT UID 解析
- 多账号去重
- 已签到跳过
- 正常领取
- `code=10001` 幂等处理
- 状态接口路径回退
- `401` 登录态失效

## 安全说明

- 脚本不会在日志中输出 Token。
- 默认签到请求只访问 `copilot.tencent.com`。
- 配置 PushPlus 后，签到摘要会发送给 PushPlus，但 Token 不会发送。
- 不要把 `.env`、青龙环境变量导出文件或真实 Token 提交到仓库。
- 本项目不会自动刷新 Token，过期后需要用户重新获取。

## 接口

| 功能 | 方法 | 路径 |
|---|---|---|
| 签到状态 | POST | `/v2/billing/meter/checkin-activity-status` |
| 状态兼容路径 | POST | `/v2/billing/meter/checkin-status` |
| 执行签到 | POST | `/v2/billing/meter/daily-checkin` |
| 积分余额 | POST | `/v2/billing/meter/get-user-resource` |

## License

[MIT](LICENSE)
