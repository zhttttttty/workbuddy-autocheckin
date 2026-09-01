#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('WorkBuddy 每日签到');
cron: 7 1,9,17 * * *

WorkBuddy 自动签到（青龙面板版）

特点：
  - 仅向 https://copilot.tencent.com 发送 WorkBuddy Token
  - 配置 WORKBUDDY_TOKEN，支持“名称#Token”及多账号
  - 兼容重复签到、接口响应包装变化和状态接口路径变化
  - 支持 Token 到期预警、积分余额、青龙 notify.py 与 PushPlus 通知
  - 仅使用 Python 标准库

本项目为非官方工具，仅供个人账号自动化使用。
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


VERSION = "2.2.0"
OFFICIAL_BASE = "https://copilot.tencent.com"
STATUS_PATHS = (
    "/v2/billing/meter/checkin-activity-status",
    "/v2/billing/meter/checkin-status",
)
CHECKIN_PATH = "/v2/billing/meter/daily-checkin"
BALANCE_PATH = "/v2/billing/meter/get-user-resource"
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


class ConfigError(ValueError):
    """环境变量配置错误。"""


class RequestError(RuntimeError):
    """网络请求在重试后仍失败。"""


@dataclass
class Account:
    index: int
    token: str
    uid: str = ""
    name: str = ""

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        if not self.uid:
            return f"账号{self.index}"
        if len(self.uid) <= 10:
            return self.uid
        return f"{self.uid[:6]}…{self.uid[-4:]}"

    def headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": f"WorkBuddy-AutoCheckin/{VERSION}",
        }
        if self.uid:
            headers["X-User-Id"] = self.uid
        return headers


def log(message: str) -> None:
    print(message, flush=True)


def split_tokens(value: str) -> List[str]:
    """单账号直接填写；多账号使用 & 分隔，也容忍换行。"""
    if not value:
        return []
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "&")
    return [item.strip() for item in normalized.split("&") if item.strip()]


def split_account_entry(entry: str) -> Tuple[str, str]:
    """解析可选的“名称#Token”；无名称时保持旧格式兼容。"""
    if "#" not in entry:
        return "", entry.strip()
    name, token = entry.split("#", 1)
    return name.strip(), token.strip()


def _b64url_json(segment: str) -> Dict[str, Any]:
    segment += "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(segment.encode("ascii"))
    value = json.loads(raw.decode("utf-8"))
    return value if isinstance(value, dict) else {}


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """仅解析 JWT payload，不验证签名；只用于读取 UID 和 exp。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        return _b64url_json(parts[1])
    except (ValueError, UnicodeError, json.JSONDecodeError, binascii.Error):
        return {}


def decode_uid(token: str) -> str:
    payload = decode_jwt_payload(token)
    for key in ("sub", "uid", "user_id", "userId"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def token_expiry(token: str, warn_days: int) -> Tuple[Optional[int], Optional[str]]:
    payload = decode_jwt_payload(token)
    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return None, None

    remaining = expires_at - int(time.time())
    if remaining <= 0:
        return 0, "Token 已过期，请重新登录 WorkBuddy 并更新环境变量"

    days = max(0, remaining // 86400)
    if remaining <= warn_days * 86400:
        return days, f"Token 约剩 {days} 天到期，请尽快更新"
    return days, None


def load_accounts() -> List[Account]:
    """读取“名称#Token”账号项，UID 自动从 JWT 解析。"""
    entries = split_tokens(os.environ.get("WORKBUDDY_TOKEN", ""))
    if not entries:
        raise ConfigError("未配置 WORKBUDDY_TOKEN")

    accounts: List[Account] = []
    seen_tokens = set()
    for entry in entries:
        name, token = split_account_entry(entry)
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        accounts.append(
            Account(
                index=len(accounts) + 1,
                token=token,
                uid=decode_uid(token),
                name=name,
            )
        )

    if not accounts:
        raise ConfigError("Token 配置为空或全部重复")
    return accounts


class HttpClient:
    def __init__(self, timeout: int = 25, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @staticmethod
    def _decode_body(raw: bytes) -> Any:
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_invalid_json": True, "_preview": text[:160]}

    def post(self, path: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        if not path.startswith("/"):
            raise ValueError("API path 必须以 / 开头")
        url = OFFICIAL_BASE + path
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        last_error: Optional[BaseException] = None

        for attempt in range(self.retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    return response.status, self._decode_body(response.read())
            except urllib.error.HTTPError as error:
                status = error.code
                parsed = self._decode_body(error.read())
                if status not in RETRYABLE_HTTP_CODES or attempt >= self.retries:
                    return status, parsed
                retry_after = error.headers.get("Retry-After", "")
                try:
                    delay = min(10.0, max(0.5, float(retry_after)))
                except ValueError:
                    delay = min(8.0, 1.2 * (2**attempt) + random.random())
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
                last_error = error
                if attempt >= self.retries:
                    break
                time.sleep(min(8.0, 1.2 * (2**attempt) + random.random()))

        reason = getattr(last_error, "reason", last_error)
        raise RequestError(f"网络请求失败：{reason}")


def dig(obj: Any, key: str) -> Any:
    """在常见响应信封及嵌套列表中查找字段。"""
    if isinstance(obj, dict):
        if key in obj and obj[key] is not None:
            return obj[key]
        for wrapper in ("data", "result", "resp", "response"):
            nested = obj.get(wrapper)
            found = dig(nested, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = dig(item, key)
            if found is not None:
                return found
    return None


def api_code(body: Any) -> Any:
    return body.get("code") if isinstance(body, dict) else None


def api_message(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    value = body.get("msg") or body.get("message") or dig(body, "msg") or dig(body, "message")
    return str(value)[:160] if value else ""


def is_auth_failure(http_code: int) -> bool:
    return http_code in {401, 403}


def is_already_checked_in(body: Any) -> bool:
    code = api_code(body)
    message = api_message(body)
    return code == 10001 or "已签" in message or "already" in message.lower()


def fmt_number(value: Any) -> str:
    try:
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:g}"
    except (TypeError, ValueError):
        return str(value)


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_dicts(value)


def fetch_status(client: HttpClient, headers: Dict[str, str]) -> Tuple[int, Any, str]:
    last: Tuple[int, Any, str] = (404, None, STATUS_PATHS[0])
    for path in STATUS_PATHS:
        status, body = client.post(path, headers)
        last = (status, body, path)
        if status not in {404, 405}:
            return last
    return last


def fetch_balance(client: HttpClient, headers: Dict[str, str]) -> Optional[int]:
    try:
        status, body = client.post(BALANCE_PATH, headers)
        if not 200 <= status < 300:
            return None
        values = []
        for item in iter_dicts(body):
            if "CycleCapacityRemainPrecise" in item:
                try:
                    values.append(int(float(item["CycleCapacityRemainPrecise"])))
                except (TypeError, ValueError):
                    continue
        return sum(values) if values else None
    except RequestError:
        return None


def status_summary(body: Any, balance: Optional[int] = None) -> str:
    parts: List[str] = []
    credit = dig(body, "today_credit")
    streak = dig(body, "streak_days")
    if credit is not None:
        parts.append(f"今日 +{fmt_number(credit)}")
    if streak is not None:
        parts.append(f"连续 {fmt_number(streak)} 天")
    if balance is not None:
        parts.append(f"余额 {balance} 积分")
    return "，".join(parts)


def result(success: bool, state: str, message: str) -> Dict[str, Any]:
    return {"success": success, "state": state, "message": message}


def checkin_one(client: HttpClient, account: Account) -> Dict[str, Any]:
    headers = account.headers()
    status_code, status_body, _ = fetch_status(client, headers)

    if is_auth_failure(status_code):
        return result(False, "NO_SESSION", f"登录态失效（HTTP {status_code}），请更新 Token")
    if not 200 <= status_code < 300:
        return result(False, "STATUS_ERROR", f"状态查询失败（HTTP {status_code}）")
    if isinstance(status_body, dict) and status_body.get("_invalid_json"):
        return result(False, "STATUS_ERROR", "状态接口返回了无法解析的数据")

    code = api_code(status_body)
    if code not in (None, 0):
        message = api_message(status_body) or f"code={code}"
        return result(False, "STATUS_ERROR", f"状态查询失败：{message}")

    if dig(status_body, "active") is False:
        activity = dig(status_body, "activity_name")
        suffix = f"（{activity}）" if activity else ""
        return result(True, "INACTIVE", f"签到活动未开启{suffix}")

    if dig(status_body, "today_checked_in") is True:
        balance = fetch_balance(client, headers)
        details = status_summary(status_body, balance)
        return result(True, "ALREADY", "今日已签到" + (f"（{details}）" if details else ""))

    claim_code, claim_body = client.post(CHECKIN_PATH, headers)
    if is_auth_failure(claim_code):
        return result(False, "NO_SESSION", f"登录态失效（HTTP {claim_code}），请更新 Token")

    if is_already_checked_in(claim_body):
        _, fresh, _ = fetch_status(client, headers)
        balance = fetch_balance(client, headers)
        details = status_summary(fresh if isinstance(fresh, dict) else status_body, balance)
        return result(True, "ALREADY", "今日已签到（服务端确认）" + (f"（{details}）" if details else ""))

    if not 200 <= claim_code < 300:
        message = api_message(claim_body)
        suffix = f"：{message}" if message else ""
        return result(False, "CLAIM_ERROR", f"签到失败（HTTP {claim_code}）{suffix}")

    claim_api_code = api_code(claim_body)
    if claim_api_code not in (None, 0):
        message = api_message(claim_body) or f"code={claim_api_code}"
        return result(False, "CLAIM_ERROR", f"签到失败：{message}")

    credit = dig(claim_body, "credit")
    if claim_body is None or (isinstance(claim_body, dict) and claim_body.get("_invalid_json")):
        _, fresh, _ = fetch_status(client, headers)
        if dig(fresh, "today_checked_in") is not True:
            return result(False, "UNKNOWN", "签到接口返回异常，且无法确认是否签到成功")
        claim_body = fresh

    _, fresh, _ = fetch_status(client, headers)
    fresh_body = fresh if isinstance(fresh, dict) else status_body
    if credit is None:
        credit = dig(fresh_body, "today_credit")

    confirmed = claim_api_code == 0 or credit is not None or dig(fresh_body, "today_checked_in") is True
    if not confirmed:
        message = api_message(claim_body)
        suffix = f"：{message}" if message else ""
        return result(False, "UNKNOWN", f"接口未提供可确认的签到成功标志{suffix}")

    streak = dig(fresh_body, "streak_days")
    is_streak_day = dig(fresh_body, "is_streak_day")
    balance = fetch_balance(client, headers)

    message_parts = [f"成功领取 {fmt_number(credit)} 积分" if credit is not None else "签到成功"]
    if is_streak_day is True:
        message_parts.append("连签奖励日")
    if streak is not None:
        message_parts.append(f"连续 {fmt_number(streak)} 天")
    if balance is not None:
        message_parts.append(f"余额 {balance} 积分")
    return result(True, "CLAIMED", "，".join(message_parts))


def send_pushplus(title: str, content: str) -> bool:
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        return False
    payload = json.dumps(
        {"token": token, "title": title, "content": content, "template": "txt"},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://www.pushplus.plus/send",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": f"WorkBuddy-AutoCheckin/{VERSION}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
        return body.get("code") == 200
    except Exception:
        return False


def send_notify(title: str, content: str) -> None:
    sent = False
    try:
        from notify import send  # type: ignore

        send(title, content)
        sent = True
    except Exception:
        pass

    if send_pushplus(title, content):
        sent = True

    if not sent:
        log("ℹ️ 未检测到可用通知渠道，结果已保留在任务日志中")


def build_client() -> HttpClient:
    return HttpClient(timeout=25, retries=2)


def main() -> int:
    log("=" * 54)
    log(f"WorkBuddy 自动签到 v{VERSION}")
    log("=" * 54)

    try:
        accounts = load_accounts()
        client = build_client()
    except ConfigError as error:
        message = f"❌ 配置错误：{error}"
        log(message)
        send_notify("WorkBuddy 签到配置错误", message)
        return 2

    warn_days = 3
    account_delay = 1.5
    reports: List[str] = []
    warnings: List[str] = []
    success_count = 0

    log(f"共 {len(accounts)} 个账号")
    for position, account in enumerate(accounts):
        log(f"\n▶ [{account.label}]")
        if not account.uid:
            log("  ℹ️ Token 中没有 UID，将仅使用 Bearer Token 请求")

        days, warning = token_expiry(account.token, warn_days)
        if warning:
            warning_line = f"[{account.label}] {warning}"
            warnings.append(warning_line)
            log(f"  ⚠️ {warning}")
        elif days is not None:
            log(f"  Token 有效期约剩 {days} 天")

        try:
            outcome = checkin_one(client, account)
        except RequestError as error:
            outcome = result(False, "NETWORK_ERROR", str(error))
        except Exception as error:  # 保证单账号异常不影响其他账号
            outcome = result(False, "UNEXPECTED", f"未预期异常：{type(error).__name__}: {error}")

        icon = "✅" if outcome["success"] else "❌"
        line = f"[{account.label}] {icon} {outcome['message']}"
        reports.append(line)
        log(f"  {icon} {outcome['message']}")
        success_count += int(outcome["success"])

        if position < len(accounts) - 1 and account_delay > 0:
            time.sleep(account_delay + random.uniform(0, min(1.0, account_delay)))

    failure_count = len(accounts) - success_count
    title_icon = "✅" if failure_count == 0 and not warnings else "⚠️" if failure_count == 0 else "❌"
    title = f"{title_icon} WorkBuddy 签到：{success_count} 成功 / {failure_count} 失败"
    summary_lines = reports[:]
    if warnings:
        summary_lines.extend(["", "Token 提醒：", *warnings])
    summary = "\n".join(summary_lines)

    log("\n" + "=" * 54)
    log(title)
    log(summary)
    log("=" * 54)
    send_notify(title, summary)
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
