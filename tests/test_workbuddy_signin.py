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
    "WB_ACCESS_TOKEN",
    "WB_ACCESS_TOKENS",
    "WB_USER_ID",
    "WB_USER_IDS",
    "WORKBUDDY_TOKEN",
    "WORKBUDDY_UID",
    "WORKBUDDY_EXTRA",
    "WB_ENTERPRISE_ID",
    "WB_ENTERPRISE_IDS",
    "WB_DOMAIN",
    "WB_DOMAINS",
    "WB_FETCH_BALANCE",
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

    def test_modern_multi_account_inline_and_jwt_uid(self):
        token = make_jwt({"sub": "jwt-user"})
        with self.clean_env(WB_ACCESS_TOKENS=f"manual-user:opaque-token,{token}"):
            accounts = wb.load_accounts()

        self.assertEqual([account.uid for account in accounts], ["manual-user", "jwt-user"])
        self.assertEqual(len(accounts), 2)

    def test_legacy_variables_remain_compatible(self):
        with self.clean_env(
            WORKBUDDY_TOKEN="token-a&token-b",
            WORKBUDDY_UID="uid-a&uid-b",
        ):
            accounts = wb.load_accounts()

        self.assertEqual([account.uid for account in accounts], ["uid-a", "uid-b"])

    def test_duplicate_tokens_are_removed(self):
        with self.clean_env(WB_ACCESS_TOKENS="uid-a:same-token,uid-b:same-token"):
            accounts = wb.load_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].uid, "uid-a")


class CheckinFlowTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {"WB_FETCH_BALANCE": "0"})
        self.env_patch.start()
        self.account = wb.Account(index=1, token="secret-token", uid="uid-1")

    def tearDown(self):
        self.env_patch.stop()

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
