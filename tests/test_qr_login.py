"""Unit tests for QR code login flow."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from xhs_cli import qr_login
from xhs_cli.command_normalizers import normalize_xhs_user_payload
from xhs_cli.exceptions import XhsApiError
from xhs_cli.qr_login import (
    BrowserQrLoginUnavailable,
    _normalize_browser_cookies,
    qrcode_login,
)


def test_chrome_login_browser_closes_after_flow_error(monkeypatch):
    manager = MagicMock()
    browser = MagicMock()
    launch = MagicMock(return_value=browser)
    manager.__enter__.return_value = SimpleNamespace(chromium=SimpleNamespace(launch=launch))
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: manager)

    with pytest.raises(XhsApiError, match="login failed"):
        with qr_login._chrome_browser() as active:
            assert active is browser
            raise XhsApiError("login failed")

    launch.assert_called_once_with(channel="chrome", headless=False)
    browser.close.assert_called_once_with()
    manager.__exit__.assert_called_once()


def test_chrome_launch_failure_reports_browser_unavailable(monkeypatch):
    manager = MagicMock()
    launch = MagicMock(side_effect=RuntimeError("Chrome executable missing"))
    manager.__enter__.return_value = SimpleNamespace(chromium=SimpleNamespace(launch=launch))
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: manager)

    with pytest.raises(BrowserQrLoginUnavailable, match="Chrome"):
        with qr_login._chrome_browser():
            pytest.fail("Must not continue login after Chrome launch failed")

    launch.assert_called_once_with(channel="chrome", headless=False)
    manager.__exit__.assert_called_once()


class _FakeQrClient:
    instances = []

    def __init__(self, cookies, request_delay=0, **kwargs):
        self.cookies = dict(cookies)
        self.activate_calls = 0
        self.status_calls = 0
        self.complete_calls = 0
        self.create_seen_web_session = None
        self.status_seen_web_session = None
        self.complete_seen_web_sessions = []
        self.self_info_calls = 0
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login_activate(self):
        self.activate_calls += 1
        if self.activate_calls == 1:
            return {"session": "guest-session", "secure_session": "guest-sec", "user_id": "guest-user"}
        return {"session": "unexpected-session", "secure_session": "unexpected-sec", "user_id": "unexpected-user"}

    def create_qr_login(self):
        self.create_seen_web_session = self.cookies.get("web_session")
        return {"qr_id": "qr-1", "code": "code-1", "url": "https://example.com/qr"}

    def check_qr_status(self, qr_id, code):
        self.status_calls += 1
        self.status_seen_web_session = self.cookies.get("web_session")
        return {"codeStatus": 2, "userId": "real-user"}

    def complete_qr_login(self, qr_id, code):
        self.complete_calls += 1
        self.complete_seen_web_sessions.append(self.cookies.get("web_session"))
        self.cookies["web_session"] = "real-session"
        self.cookies["web_session_sec"] = "real-sec"
        return {
            "code_status": 2,
            "login_info": {
                "user_id": "real-user",
                "session": "real-session",
                "secure_session": "real-sec",
            },
        }

    def get_self_info(self):
        self.self_info_calls += 1
        return {
            "user_id": "real-user",
            "basic_info": {
                "user_id": "real-user",
                "nickname": "Alice",
                "red_id": "alice001",
            },
        }


class _MismatchQrClient(_FakeQrClient):
    def complete_qr_login(self, qr_id, code):
        self.complete_calls += 1
        self.complete_seen_web_sessions.append(self.cookies.get("web_session"))
        self.cookies["web_session"] = "wrong-session"
        self.cookies["web_session_sec"] = "wrong-sec"
        return {
            "code_status": 2,
            "login_info": {
                "user_id": "guest-user",
                "session": "wrong-session",
                "secure_session": "wrong-sec",
            },
        }

    def get_self_info(self):
        self.self_info_calls += 1
        return {
            "user_id": "guest-user",
            "basic_info": {
                "user_id": "guest-user",
                "nickname": "Guest",
                "red_id": "",
            },
        }


class _SelfInfoFallbackQrClient(_FakeQrClient):
    def complete_qr_login(self, qr_id, code):
        self.complete_calls += 1
        self.complete_seen_web_sessions.append(self.cookies.get("web_session"))
        self.cookies["web_session"] = "real-session"
        self.cookies["web_session_sec"] = "real-sec"
        return {
            "code_status": 2,
            "login_info": {
                "user_id": "guest-user",
                "session": "real-session",
                "secure_session": "real-sec",
            },
        }


def test_qrcode_login_completes_after_confirmation_and_saves_real_session(monkeypatch):
    saved = []

    monkeypatch.setattr("xhs_cli.qr_login.XhsClient", _FakeQrClient)
    monkeypatch.setattr("xhs_cli.qr_login._generate_a1", lambda: "a1-fixed")
    monkeypatch.setattr("xhs_cli.qr_login._generate_webid", lambda: "webid-fixed")
    monkeypatch.setattr("xhs_cli.qr_login._display_qr_in_terminal", lambda data: True)
    monkeypatch.setattr("xhs_cli.qr_login.time.sleep", lambda seconds: None)
    monkeypatch.setattr("xhs_cli.qr_login.save_cookies", lambda cookies: saved.append(cookies))

    cookies = qrcode_login(timeout_s=1)
    client = _FakeQrClient.instances[-1]

    assert client.create_seen_web_session == "guest-session"
    assert client.status_seen_web_session == "guest-session"
    assert client.activate_calls == 1
    assert client.complete_calls == 1
    assert client.complete_seen_web_sessions == ["guest-session"]
    assert cookies == {
        "a1": "a1-fixed",
        "webId": "webid-fixed",
        "web_session": "real-session",
        "web_session_sec": "real-sec",
    }
    assert saved == [cookies]


def test_qrcode_login_accepts_confirmed_user_from_self_info_fallback(monkeypatch):
    saved = []

    monkeypatch.setattr("xhs_cli.qr_login.XhsClient", _SelfInfoFallbackQrClient)
    monkeypatch.setattr("xhs_cli.qr_login._generate_a1", lambda: "a1-fixed")
    monkeypatch.setattr("xhs_cli.qr_login._generate_webid", lambda: "webid-fixed")
    monkeypatch.setattr("xhs_cli.qr_login._display_qr_in_terminal", lambda data: True)
    monkeypatch.setattr("xhs_cli.qr_login.time.sleep", lambda seconds: None)
    monkeypatch.setattr("xhs_cli.qr_login.save_cookies", lambda cookies: saved.append(cookies))

    cookies = qrcode_login(timeout_s=1)
    client = _SelfInfoFallbackQrClient.instances[-1]

    assert client.activate_calls == 1
    assert client.complete_calls == 1
    assert client.self_info_calls >= 1
    assert cookies == {
        "a1": "a1-fixed",
        "webId": "webid-fixed",
        "web_session": "real-session",
        "web_session_sec": "real-sec",
    }
    assert saved == [cookies]


def test_qrcode_login_rejects_mismatched_confirmed_user(monkeypatch):
    monkeypatch.setattr("xhs_cli.qr_login.XhsClient", _MismatchQrClient)
    monkeypatch.setattr("xhs_cli.qr_login._generate_a1", lambda: "a1-fixed")
    monkeypatch.setattr("xhs_cli.qr_login._generate_webid", lambda: "webid-fixed")
    monkeypatch.setattr("xhs_cli.qr_login._display_qr_in_terminal", lambda data: True)
    monkeypatch.setattr("xhs_cli.qr_login.time.sleep", lambda seconds: None)
    monkeypatch.setattr("xhs_cli.qr_login.save_cookies", lambda cookies: None)

    with pytest.raises(XhsApiError, match="completion never returned"):
        qrcode_login(timeout_s=1)


def test_qrcode_login_prefers_browser_assisted_backend(monkeypatch):
    saved = []

    monkeypatch.setattr(
        "xhs_cli.qr_login._browser_assisted_qrcode_login",
        lambda **kwargs: {
            "a1": "a1-browser",
            "webId": "webid-browser",
            "web_session": "0400-browser",
            "web_session_sec": "secure-browser",
            "id_token": "token-browser",
        },
    )

    cookies = qrcode_login(timeout_s=1, prefer_browser_assisted=True)

    assert cookies["web_session"] == "0400-browser"
    assert cookies["id_token"] == "token-browser"
    assert saved == []


def test_qrcode_login_reports_chrome_failure_without_silent_http_fallback(monkeypatch):
    monkeypatch.setattr(
        "xhs_cli.qr_login._browser_assisted_qrcode_login",
        lambda **kwargs: (_ for _ in ()).throw(BrowserQrLoginUnavailable("missing Chrome")),
    )
    monkeypatch.setattr(
        "xhs_cli.qr_login._http_qrcode_login",
        lambda **kwargs: pytest.fail("Chrome failure must not start another login flow"),
    )

    with pytest.raises(BrowserQrLoginUnavailable, match="missing Chrome"):
        qrcode_login(timeout_s=1, prefer_browser_assisted=True)


def test_normalize_browser_cookies_uses_allowlist():
    cookies = _normalize_browser_cookies([
        {"name": "a1", "value": "a1-value", "domain": ".xiaohongshu.com"},
        {"name": "web_session", "value": "session-value", "domain": ".xiaohongshu.com"},
        {"name": "customer-sso-sid", "value": "skip-me", "domain": ".xiaohongshu.com"},
        {"name": "creator_only", "value": "skip-me-too", "domain": "creator.xiaohongshu.com"},
    ])

    assert cookies == {
        "a1": "a1-value",
        "web_session": "session-value",
    }


def test_normalize_xhs_user_payload_reads_basic_info():
    user = normalize_xhs_user_payload({
        "guest": False,
        "basic_info": {
            "user_id": "user-1",
            "nickname": "Alice",
            "red_id": "alice001",
            "ip_location": "上海",
            "desc": "hello",
        },
    })

    assert user == {
        "id": "user-1",
        "name": "Alice",
        "username": "alice001",
        "nickname": "Alice",
        "red_id": "alice001",
        "ip_location": "上海",
        "desc": "hello",
        "guest": False,
    }
