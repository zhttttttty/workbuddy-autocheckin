import base64
import json
import os
import pathlib
import sys
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import workbuddy_signin as wb  # noqa: E402


RELEVANT_ENV = {
    "WORKBUDDY_ACCOUNTS",
    "PUSHPLUS_TOKEN",
}


def make_jwt(payload):
    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode(payload)}.signature"


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.paths = []

    def post(self, path, headers, payload=None):
        self.paths.append(path)
        if not self.responses:
            raise AssertionError(f"没有为 {path} 准备模拟响应")
        return self.responses.pop(0)


class AccountParsingTests(unittest.TestCase):
    def clean_env(self, **values):
        env = {key: value for key, value in os.environ.items() if key not in RELEVANT_ENV}
        env.update(values)
        return patch.dict(os.environ, env, clear=True)

    def test_single_token_and_jwt_uid(self):
        token = make_jwt({"sub": "jwt-user"})
        value = json.dumps([{"name": "小明", "accessToken": token}])
        with self.clean_env(WORKBUDDY_ACCOUNTS=value):
            accounts = wb.load_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].uid, "jwt-user")
        self.assertEqual(accounts[0].label, "小明")

    def test_multi_account_json_array(self):
        value = json.dumps(
            [
                {"name": "张三", "accessToken": "token-a"},
                {"name": "李四", "accessToken": "token-b"},
            ]
        )
        with self.clean_env(WORKBUDDY_ACCOUNTS=value):
            accounts = wb.load_accounts()

        self.assertEqual([account.token for account in accounts], ["token-a", "token-b"])
        self.assertEqual([account.name for account in accounts], ["张三", "李四"])
        self.assertEqual([account.label for account in accounts], ["张三", "李四"])

    def test_name_is_optional(self):
        value = json.dumps([{"accessToken": "token-a"}])
        with self.clean_env(WORKBUDDY_ACCOUNTS=value):
            accounts = wb.load_accounts()

        self.assertEqual(accounts[0].name, "")
        self.assertEqual(accounts[0].label, "账号1")

    def test_duplicate_tokens_are_removed(self):
        value = json.dumps(
            [
                {"name": "首次配置", "accessToken": "same-token"},
                {"name": "重复配置", "accessToken": "same-token"},
            ]
        )
        with self.clean_env(WORKBUDDY_ACCOUNTS=value):
            accounts = wb.load_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, "首次配置")

    def test_invalid_json_has_clear_error(self):
        with self.clean_env(WORKBUDDY_ACCOUNTS='[{"name":"小明",}]'):
            with self.assertRaisesRegex(wb.ConfigError, "不是有效的 JSON"):
                wb.load_accounts()

    def test_root_must_be_non_empty_array(self):
        with self.clean_env(WORKBUDDY_ACCOUNTS='{"name":"小明","accessToken":"token-a"}'):
            with self.assertRaisesRegex(wb.ConfigError, "必须是非空 JSON 数组"):
                wb.load_accounts()

    def test_each_account_requires_access_token(self):
        with self.clean_env(WORKBUDDY_ACCOUNTS='[{"name":"小明"}]'):
            with self.assertRaisesRegex(wb.ConfigError, "缺少有效的 accessToken"):
                wb.load_accounts()

    def test_legacy_token_field_is_rejected(self):
        with self.clean_env(WORKBUDDY_ACCOUNTS='[{"name":"小明","token":"token-a"}]'):
            with self.assertRaisesRegex(wb.ConfigError, "缺少有效的 accessToken"):
                wb.load_accounts()


class CheckinFlowTests(unittest.TestCase):
    def setUp(self):
        self.balance_patch = patch.object(wb, "fetch_balance", return_value=None)
        self.balance_patch.start()
        self.account = wb.Account(index=1, token="secret-token", uid="uid-1")

    def tearDown(self):
        self.balance_patch.stop()

    def test_status_true_skips_claim(self):
        client = FakeClient([(200, {"code": 0, "data": {"today_checked_in": True, "streak_days": 2}})])

        outcome = wb.checkin_one(client, self.account)

        self.assertTrue(outcome["success"])
        self.assertEqual(outcome["state"], "ALREADY")
        self.assertEqual(client.paths, [wb.STATUS_PATHS[0]])

    def test_claim_success_refreshes_status(self):
        client = FakeClient(
            [
                (200, {"code": 0, "data": {"today_checked_in": False}}),
                (200, {"code": 0, "data": {"credit": 100}}),
                (200, {"code": 0, "data": {"today_checked_in": True, "streak_days": 3}}),
            ]
        )

        outcome = wb.checkin_one(client, self.account)

        self.assertTrue(outcome["success"])
        self.assertEqual(outcome["state"], "CLAIMED")
        self.assertIn("100", outcome["message"])

    def test_code_10001_is_successful_already_state(self):
        client = FakeClient(
            [
                (200, {"code": 0, "data": {"today_checked_in": False}}),
                (400, {"code": 10001, "msg": "今日已签到"}),
                (200, {"code": 0, "data": {"today_checked_in": True}}),
            ]
        )

        outcome = wb.checkin_one(client, self.account)

        self.assertTrue(outcome["success"])
        self.assertEqual(outcome["state"], "ALREADY")

    def test_status_endpoint_falls_back_on_404(self):
        client = FakeClient(
            [
                (404, {"message": "not found"}),
                (200, {"code": 0, "data": {"today_checked_in": True}}),
            ]
        )

        outcome = wb.checkin_one(client, self.account)

        self.assertTrue(outcome["success"])
        self.assertEqual(client.paths, list(wb.STATUS_PATHS))

    def test_401_is_reported_as_expired_session(self):
        client = FakeClient([(401, {"message": "unauthorized"})])

        outcome = wb.checkin_one(client, self.account)

        self.assertFalse(outcome["success"])
        self.assertEqual(outcome["state"], "NO_SESSION")

    def test_ambiguous_http_200_is_not_false_success(self):
        client = FakeClient(
            [
                (200, {"code": 0, "data": {"today_checked_in": False}}),
                (200, {"message": "unexpected response"}),
                (200, {"code": 0, "data": {"today_checked_in": False}}),
            ]
        )

        outcome = wb.checkin_one(client, self.account)

        self.assertFalse(outcome["success"])
        self.assertEqual(outcome["state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
