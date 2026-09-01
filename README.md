# WorkBuddy AutoCheckin

WorkBuddy 每日积分自动签到脚本，面向青龙面板，也可以直接在 Linux、macOS 和 Windows 上运行。

项目以稳定签到为重点：支持多账号、重复运行、JWT 自动解析 UID、Token 到期提醒、积分余额、请求重试及青龙通知。脚本仅使用 Python 标准库，不需要安装 `requests`。

> 本项目是非官方个人自动化工具。接口可能随 WorkBuddy 更新而变化，请只用于本人账号，并自行评估账号规则与使用风险。

## 功能

- 调用腾讯 WorkBuddy 官方接口完成每日签到。
- 先查询签到状态，未签到时才领取；服务端返回 `code=10001` 时按“今日已签到”处理。
- 状态接口出现 `404/405` 时自动尝试兼容路径。
- 只需配置一个 `WORKBUDDY_TOKEN`；支持 `名称#Token`，多账号使用 `&` 分隔。
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

### 1. 必填变量 `WORKBUDDY_TOKEN`

脚本只要求配置一个环境变量，变量名称必须是：

```text
WORKBUDDY_TOKEN
```

变量值由“账号名称”和“完整 Token”组成，基本格式为：

```text
账号名称#完整Token
```

各部分含义如下：

| 内容 | 是否必填 | 作用 | 示例 |
|---|---|---|---|
| 账号名称 | 否 | 只用于日志和通知，方便区分账号 | `公司账号` |
| `#` | 有名称时必填 | 分隔账号名称与 Token | `#` |
| 完整 Token | 是 | WorkBuddy 登录凭据，从 `auth.accessToken` 复制 | `eyJhbGciOi...` |
| `&` | 多账号时必填 | 分隔两个账号 | `&` |

完整格式可以理解为：

```text
名称1#Token1&名称2#Token2&名称3#Token3
```

> `名称1`、`Token1` 只是格式说明，不能原样填写。必须替换成自己的名称和从登录态文件复制的完整 Token。

### 2. 青龙面板填写位置

进入青龙面板 → **环境变量** → **新建变量**。青龙表单通常包含“名称”“值”“备注”等输入框：

| 青龙输入框 | 应填写的内容 |
|---|---|
| 名称 | `WORKBUDDY_TOKEN` |
| 值 | `账号名称#完整Token` |
| 备注 | 可留空，脚本不会读取这里的内容 |

注意：在青龙表单里，“名称”和“值”是两个不同的输入框。不要把
`WORKBUDDY_TOKEN=` 一起粘贴到“值”输入框中。

#### 青龙单账号模板

```text
名称：WORKBUDDY_TOKEN
值：小明#在这里粘贴小明账号的完整accessToken
备注：可留空
```

假设复制出来的 Token 是 `eyJhbGciOiJIUzI1NiJ9.abc123.signature`，实际填写效果如下：

```text
名称：WORKBUDDY_TOKEN
值：小明#eyJhbGciOiJIUzI1NiJ9.abc123.signature
```

脚本日志会显示：

```text
▶ [小明]
  ✅ 签到成功
```

#### 青龙双账号模板

只创建一个 `WORKBUDDY_TOKEN` 变量，不要创建 `WORKBUDDY_TOKEN1`、
`WORKBUDDY_TOKEN2`。两个账号之间使用 `&` 连接：

```text
名称：WORKBUDDY_TOKEN
值：小明#小明的完整Token&小红#小红的完整Token
备注：可留空
```

例如：

```text
名称：WORKBUDDY_TOKEN
值：小明#eyJAAA.aaa.sig&小红#eyJBBB.bbb.sig
```

脚本会把它解析为：

| 顺序 | 日志名称 | 使用的 Token |
|---|---|---|
| 账号 1 | 小明 | `eyJAAA.aaa.sig` |
| 账号 2 | 小红 | `eyJBBB.bbb.sig` |

日志会分别显示：

```text
▶ [小明]
  ✅ 签到成功

▶ [小红]
  ✅ 今日已签到
```

#### 青龙三个及更多账号模板

继续在后面添加 `&名称#Token` 即可：

```text
名称：WORKBUDDY_TOKEN
值：小明#Token1&小红#Token2&小刚#Token3
```

### 3. 不填写账号名称也可以

账号名称是可选内容。只填写 Token 时，原有格式仍然有效。

单账号无名称：

```text
名称：WORKBUDDY_TOKEN
值：完整Token
```

多账号无名称：

```text
名称：WORKBUDDY_TOKEN
值：Token1&Token2&Token3
```

命名账号与未命名账号也可以混合：

```text
名称：WORKBUDDY_TOKEN
值：小明#Token1&Token2&小刚#Token3
```

未填写名称时，脚本优先显示从 JWT 中解析并脱敏后的 UID；如果 Token
中无法解析 UID，则按顺序显示 `账号1`、`账号2`。

### 4. 填写规则和注意事项

1. Token 必须完整复制，不能只复制开头，也不能包含示例中的 `...`。
2. Token 前面不要添加 `Bearer `，脚本会自动添加认证前缀。
3. `#` 用于分隔名称和 Token；账号名称中不能包含 `#`。
4. `&` 用于分隔多个账号；账号名称中不能包含 `&`。
5. 推荐不要在 `#` 或 `&` 两侧添加空格，虽然脚本会自动清理首尾空格。
6. 青龙“备注”字段不会作为日志名称；日志名称必须写在变量值的 Token 前面。
7. 多账号仍然只创建一个 `WORKBUDDY_TOKEN` 环境变量。
8. Token 属于登录凭据，不要发到群聊、Issue、截图或公开仓库。

### 5. 常见错误示例

错误：把变量赋值表达式全部填进青龙的“值”输入框：

```text
值：WORKBUDDY_TOKEN=小明#eyJAAA.aaa.sig
```

正确：青龙“名称”和“值”分开填写：

```text
名称：WORKBUDDY_TOKEN
值：小明#eyJAAA.aaa.sig
```

错误：为每个账号创建不同的变量名：

```text
WORKBUDDY_TOKEN1
WORKBUDDY_TOKEN2
```

正确：只创建一个变量，账号之间用 `&` 分隔：

```text
名称：WORKBUDDY_TOKEN
值：小明#Token1&小红#Token2
```

错误：Token 不完整或把省略号也复制进去：

```text
值：小明#eyJxxxx...
```

正确：粘贴登录态文件中 `auth.accessToken` 的全部内容。

### 6. 其他配置

UID、重试次数、超时时间、积分余额查询、Token 到期提醒和多账号间隔均由脚本自动处理，不需要另外配置。

如果需要 PushPlus 通知，再创建一个可选环境变量：

```text
名称：PUSHPLUS_TOKEN
值：你的完整 PushPlus Token
备注：可留空
```

不使用 PushPlus 时，不需要创建 `PUSHPLUS_TOKEN`。青龙面板已有的
`notify.py` 通知渠道也不需要在本脚本中重复配置。

## 本地运行

Linux/macOS：

```bash
export WORKBUDDY_TOKEN='张三#eyJxxxx...'
python3 workbuddy_signin.py
```

Windows PowerShell：

```powershell
$env:WORKBUDDY_TOKEN = '张三#eyJxxxx...'
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
- `名称#Token` 解析及名称缺省回退
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
