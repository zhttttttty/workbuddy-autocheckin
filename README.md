# WorkBuddy AutoCheckin

WorkBuddy 每日积分自动签到脚本，面向青龙面板，也可以直接在 Linux、macOS 和 Windows 上运行。

项目以稳定签到为重点：支持多账号、重复运行、JWT 自动解析 UID、Token 到期提醒、积分余额、请求重试及青龙通知。脚本仅使用 Python 标准库，不需要安装 `requests`。

> 本项目是非官方个人自动化工具。接口可能随 WorkBuddy 更新而变化，请只用于本人账号，并自行评估账号规则与使用风险。

## 功能

- 调用腾讯 WorkBuddy 官方接口完成每日签到。
- 先查询签到状态，未签到时才领取；服务端返回 `code=10001` 时按“今日已签到”处理。
- 状态接口出现 `404/405` 时自动尝试兼容路径。
- 只需配置一个 `WORKBUDDY_TOKEN`；多账号使用 `&` 分隔。
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

先在 WorkBuddy 桌面端正常登录，再找到登录态文件：

| 系统 | 新版登录态文件 |
|---|---|
| Windows | `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` |
| Windows 回退 | `%APPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` |
| macOS | `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` |
| Linux | `~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` |

打开 JSON 文件，复制 `auth.accessToken` 的完整内容即可。UID 会由脚本自动解析，不需要另外查找。

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

只需要一个必填变量：

```text
变量名：WORKBUDDY_TOKEN
变量值：从登录态文件复制的完整 accessToken
```

单账号示例：

```text
WORKBUDDY_TOKEN=eyJxxxx...
```

多账号仍然使用同一个变量，Token 之间用 `&` 分隔：

```text
WORKBUDDY_TOKEN=eyJ账号1...&eyJ账号2...
```

UID、重试次数、超时时间、积分余额查询、Token 到期提醒和多账号间隔均由脚本自动处理，不需要配置。

如果你希望额外使用 PushPlus，再添加一个可选变量：

```text
PUSHPLUS_TOKEN=你的PushPlus Token
```

青龙面板原有的通知渠道不需要新增变量。

## 本地运行

Linux/macOS：

```bash
export WORKBUDDY_TOKEN='eyJxxxx...'
python3 workbuddy_signin.py
```

Windows PowerShell：

```powershell
$env:WORKBUDDY_TOKEN = 'eyJxxxx...'
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

- 单账号与多账号 Token 解析
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
