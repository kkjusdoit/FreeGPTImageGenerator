import sys
import types
import unittest
import asyncio
from unittest.mock import patch


try:
    import curl_cffi  # noqa: F401
except Exception:
    fake_requests_module = types.SimpleNamespace(get=None, post=None, patch=None, delete=None)

    class _FakeCurlMime:
        def addpart(self, **kwargs):
            return None

    sys.modules["curl_cffi"] = types.SimpleNamespace(
        requests=fake_requests_module,
        CurlMime=_FakeCurlMime,
    )

sys.modules.setdefault("cloudflare", types.SimpleNamespace(Cloudflare=object))
sys.modules.setdefault(
    "utils.integrations.ai_service",
    types.SimpleNamespace(AIService=object),
)
sys.modules.setdefault(
    "utils.integrations.tg_notifier",
    types.SimpleNamespace(
        send_tg_msg_async=lambda *args, **kwargs: None,
        send_tg_msg_sync=lambda *args, **kwargs: None,
    ),
)
sys.modules.setdefault(
    "utils.email_providers.gmail_service",
    types.SimpleNamespace(get_gmail_otp_via_oauth=lambda *args, **kwargs: ""),
)
sys.modules.setdefault(
    "utils.email_providers.duckmail_service",
    types.SimpleNamespace(DuckMailService=object),
)

from routers import account_routes
from routers import system_routes
from utils import db_manager


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class CPAAuthFlowTests(unittest.TestCase):
    def test_classify_token_payload_marks_reg_only_as_non_cpa(self):
        result = db_manager.classify_token_payload({"status": "仅注册成功"})

        self.assertEqual("reg_only", result["account_type"])
        self.assertFalse(result["cpa_eligible"])
        self.assertFalse(result["maintenance_ready"])

    def test_classify_token_payload_marks_refresh_only_as_maintenance_ready(self):
        result = db_manager.classify_token_payload({"refresh_token": "rt_demo"})

        self.assertEqual("待刷新", result["status"])
        self.assertEqual("credential", result["account_type"])
        self.assertFalse(result["cpa_eligible"])
        self.assertTrue(result["maintenance_ready"])

    def test_account_action_rejects_reg_only_for_cpa_push(self):
        with patch("routers.account_routes.db_manager.get_token_by_email", return_value={"status": "仅注册成功"}):
            result = account_routes.account_action({"email": "demo@example.com", "action": "push"}, token="ok")

        self.assertEqual("error", result["status"])
        self.assertIn("已排除出后续 CPA 流程", result["message"])

    def test_start_endpoint_is_disabled_for_registration_flow(self):
        result = asyncio.run(system_routes.start_task(token="ok"))

        self.assertEqual("error", result["status"])
        self.assertIn("自动注册/补货流程已下线", result["message"])

    def test_import_authorized_accounts_parses_manual_authorized_lines(self):
        raw_text = "demo@example.com----pass123----client-1----rt_abc\ninvalid-line"
        with patch("routers.account_routes.db_manager.import_authorized_accounts", return_value=(1, 0)) as mocked_import:
            result = asyncio.run(account_routes.import_authorized_accounts(
                account_routes.ImportAuthorizedAccountReq(raw_text=raw_text),
                token="ok",
            ))

        self.assertEqual("success", result["status"])
        mocked_import.assert_called_once()
        parsed = mocked_import.call_args[0][0]
        self.assertEqual(1, len(parsed))
        self.assertEqual("demo@example.com", parsed[0]["email"])
        self.assertEqual("client-1", parsed[0]["client_id"])

    def test_get_cloud_accounts_returns_empty_list_when_cpa_fetch_fails(self):
        with patch.object(account_routes.cfg, "CPA_API_URL", "https://cpa.example.com", create=True), patch.object(
            account_routes.cfg, "CPA_API_TOKEN", "bad-token", create=True
        ), patch(
            "curl_cffi.requests.get",
            return_value=_Resp(401, text="Unauthorized"),
        ):
            result = account_routes.get_cloud_accounts(types="cpa", page=1, page_size=50, token="ok")

        self.assertEqual("success", result["status"])
        self.assertEqual([], result["data"])
        self.assertEqual(0, result["total"])


if __name__ == "__main__":
    unittest.main()
