"""Regression checks for the combined local PR build; all requests are mocked."""

import json

import httpx
import pytest
from click.testing import CliRunner

from xhs_cli.cli import cli
from xhs_cli.client import XhsClient
from xhs_cli.cookies import extract_browser_cookies
from xhs_cli.exceptions import XhsApiError
from xhs_cli.formatter_normalizers import normalize_creator_note_data


def test_hermes_never_attempts_browser_decryption(monkeypatch):
    def unexpected(*args):
        pytest.fail("browser extraction must stay disabled")

    monkeypatch.setattr("xhs_cli.cookies._extract_in_process", unexpected)
    monkeypatch.setattr("xhs_cli.cookies._extract_via_subprocess", unexpected)
    assert extract_browser_cookies("chrome") is None
    assert extract_browser_cookies("auto") is None


@pytest.mark.parametrize("endpoint", ["/api/im/web/short_link/send_message", "/web_api/sns/v2/note"])
@pytest.mark.parametrize("failure", ["timeout", "503"])
def test_sensitive_writes_are_not_replayed(endpoint, failure):
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("unknown outcome", request=request)
        return httpx.Response(503, request=request)

    with XhsClient({"a1": "fake"}, request_delay=0) as client:
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(respond))
        with pytest.raises(XhsApiError, match="not retried"):
            client._request_with_retry("POST", "https://example.invalid" + endpoint, json={})
    assert len(calls) == 1


def test_video_payload_and_original_image_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(XhsClient, "_creator_post", lambda self, uri, data: calls.append(("creator", uri, data)) or {})
    monkeypatch.setattr(
        XhsClient, "_main_api_post",
        lambda self, uri, data, headers=None: calls.append(("main", uri, data)) or {},
    )
    with XhsClient({"a1": "fake"}) as client:
        client.create_video_note("中文", "正文", "vid", cover_file_id="cover", is_private=True)
        client.create_image_note("image", "body", ["img"])
    video = calls[0][2]
    assert calls[0][:2] == ("creator", "/web_api/sns/v2/note")
    assert video["common"]["type"] == "video"
    assert video["video_info"]["file_id"] == "vid"
    assert video["image_info"]["images"][0]["file_id"] == "cover"
    assert video["common"]["privacy_info"]["type"] == 1
    assert calls[1][0] == "main"


def test_video_json_and_topics(tmp_path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"mock upload bytes")
    captured = {}

    class FakeClient:
        def get_video_upload_permit(self):
            return {"fileId": "vid", "token": "fake"}

        def upload_video(self, file_id, token, path):
            assert file_id == "vid" and path == str(video)

        def search_topics(self, name):
            return {"topic_info_dtos": [{"id": name, "name": name}]}

        def create_video_note(self, **kwargs):
            captured.update(kwargs)
            return {"note_id": "new-note"}

    monkeypatch.setattr("xhs_cli.commands._common.run_client_action", lambda ctx, action: action(FakeClient()))
    result = CliRunner().invoke(cli, [
        "post-video", "--title", "中文", "--body", "正文 #旅行", "--video", str(video),
        "--topic", "旅行", "--topic", "美食", "--private", "--json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["note_id"] == "new-note"
    assert [topic["name"] for topic in captured["topics"]] == ["旅行", "美食"]
    assert captured["is_private"] is True


def test_missing_cover_fails_before_upload(tmp_path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"mock upload bytes")
    monkeypatch.setattr("xhs_cli.commands._common.run_client_action", lambda ctx, action: action(object()))
    result = CliRunner().invoke(cli, [
        "post-video", "--title", "t", "--body", "b", "--video", str(video),
        "--cover", str(tmp_path / "missing.jpg"), "--json",
    ])
    assert result.exit_code != 0
    assert "Cover image not found" in json.loads(result.stdout)["error"]["message"]


def test_creator_analysis_endpoint_and_counts(monkeypatch):
    captured = {}

    def fake_get(self, uri, params):
        captured.update(uri=uri, params=params)
        return {"notes": [{"read_count": 12, "imp_count": 30, "coverClickRate": 0.4}]}

    monkeypatch.setattr(XhsClient, "_creator_get", fake_get)
    with XhsClient({"a1": "fake"}) as client:
        result = client.get_creator_note_analyze_list(page_num=2, page_size=5)
    assert captured["uri"] == "/api/galaxy/creator/datacenter/note/analyze/list"
    assert captured["params"]["page_num"] == 2
    row = normalize_creator_note_data(result)[0]
    assert row["view_count"] == "12"
    assert row["click_rate"] == "40.0%"


def test_creator_analysis_nested_failure_is_not_success(monkeypatch):
    monkeypatch.setattr(
        XhsClient, "_creator_get",
        lambda *args: {"result": {"success": False, "code": 123, "message": "denied"}},
    )
    with XhsClient({"a1": "fake"}) as client:
        with pytest.raises(XhsApiError, match="denied"):
            client.get_creator_note_analyze_list()


def test_creator_analysis_wrapped_nullable_rate():
    rows = normalize_creator_note_data({"result": {"data": {"notes": [{"coverClickRate": None}]}}})
    assert rows[0]["click_rate"] == "-"


def test_search_users_pagination_payload(monkeypatch):
    captured = {}

    def fake_post(self, uri, data):
        captured.update(uri=uri, data=data)
        return {"user_info_dtos": []}

    monkeypatch.setattr(XhsClient, "_creator_post", fake_post)
    with XhsClient({"a1": "fake"}) as client:
        client.search_users("摄影", page=3, page_size=10, search_id="same-session")
    assert captured["uri"] == "/web_api/sns/v1/search/user_info"
    assert captured["data"]["page"] == {"page": 3, "page_size": 10}
    assert captured["data"]["search_id"] == "same-session"


def test_search_user_cli_passes_pagination(monkeypatch):
    captured = {}

    class FakeClient:
        def search_users(self, keyword, **kwargs):
            captured.update(keyword=keyword, **kwargs)
            return {"user_info_dtos": []}

    monkeypatch.setattr("xhs_cli.commands._common.run_client_action", lambda ctx, action: action(FakeClient()))
    result = CliRunner().invoke(cli, [
        "search-user", "摄影", "--page", "2", "--page-size", "10", "--search-id", "session", "--json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True
    assert captured == {"keyword": "摄影", "page": 2, "page_size": 10, "search_id": "session"}


def test_search_user_rejects_invalid_page_before_request():
    result = CliRunner().invoke(cli, ["search-user", "摄影", "--page", "0"])
    assert result.exit_code == 2
    assert "x>=1" in result.output


def test_following_pagination_and_status_preserved(monkeypatch):
    requested = []

    def fake_get(self, uri, params):
        requested.append((uri, params))
        return {"follow_user_d_t_o_list": [{"user_id": "peer", "nick_name": "name", "status": 2}]}

    monkeypatch.setattr(XhsClient, "_main_api_get", fake_get)
    with XhsClient({"a1": "fake"}) as client:
        data = client.get_following(page=2, page_size=1)
    assert requested == [("/api/im/web/users/following/all", {"page": 2, "size": 1})]
    assert data["users"][0]["status"] == 2
    assert data["has_more"] is True
    assert data["next_page"] == 3
    assert data["pagination_inferred"] is True


def test_following_reject_unknown_shape(monkeypatch):
    monkeypatch.setattr(XhsClient, "_main_api_get", lambda *args, **kwargs: {})
    with XhsClient({"a1": "fake"}) as client:
        with pytest.raises(XhsApiError, match="Unexpected"):
            client.get_following()


def test_browsing_history_cursor_and_account_source(monkeypatch):
    captured = {}

    def fake_get(self, uri, params):
        captured.update(uri=uri, params=params)
        return {"result": {"success": True, "code": 0}, "data": [{"id": "note", "browse_time": 123}],
                "has_no_more": False, "next_cursor": "next"}

    monkeypatch.setattr(XhsClient, "_main_api_get", fake_get)
    with XhsClient({"a1": "fake"}) as client:
        data = client.get_browsing_history(cursor="previous", note_index=20)
    assert captured["uri"] == "/api/sns/web/v1/common/dual_feed"
    assert captured["params"]["scene"] == "browse_history"
    assert captured["params"]["cursor_score"] == "previous"
    assert captured["params"]["note_index"] == 20
    assert data["cursor"] == "next"
    assert data["has_more"] is True
    assert data["next_note_index"] == 21
    assert data["notes"][0]["browse_time"] == 123


@pytest.mark.parametrize("response", [
    {"result": {"success": False, "code": 1, "message": "denied"}},
    {"data": []},
])
def test_browsing_history_reject_failure_or_missing_pagination(monkeypatch, response):
    monkeypatch.setattr(XhsClient, "_main_api_get", lambda *args: response)
    with XhsClient({"a1": "fake"}) as client:
        with pytest.raises(XhsApiError):
            client.get_browsing_history()


@pytest.mark.parametrize("command,expected", [
    (["following", "--page", "2", "--page-size", "1", "--json"], {"page": 2, "page_size": 1}),
    (["history", "--cursor", "next", "--note-index", "20", "--json"], {"cursor": "next", "note_index": 20}),
])
def test_following_and_history_cli_pass_pagination(monkeypatch, command, expected):
    captured = {}

    class FakeClient:
        def get_following(self, **kwargs):
            captured.update(kwargs)
            return {"users": []}

        def get_browsing_history(self, **kwargs):
            captured.update(kwargs)
            return {"notes": []}

    monkeypatch.setattr("xhs_cli.commands._common.run_client_action", lambda ctx, action: action(FakeClient()))
    result = CliRunner().invoke(cli, command)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True
    assert captured == expected
