import json

import pytest
from click.testing import CliRunner

from xhs_cli.cli import cli
from xhs_cli.commands.creator import extract_hashtags, format_body_hashtags


def test_extract_hashtags():
    # Normal case
    assert extract_hashtags("This is a #test and another #hashtag") == ["test", "hashtag"]

    # Empty body
    assert extract_hashtags("") == []

    # URL fragment shouldn't match
    assert extract_hashtags("Visit https://example.com#section for more info") == []

    # Consecutive tags without spaces — only the first is preceded by whitespace
    assert extract_hashtags("Mixed #one#two#three") == ["one"]

    # Tags at start of line
    assert extract_hashtags("#start of line") == ["start"]

    # Mix of languages
    assert extract_hashtags("测试 #中文标签 和 #english tag") == ["中文标签", "english"]

    # Trailing hashtag
    assert extract_hashtags("This is #trailing") == ["trailing"]

    # Pure hashtag body
    assert extract_hashtags("#a #b #c") == ["a", "b", "c"]

    # Emoji hashtag
    assert extract_hashtags("Let's go #🎉party") == ["🎉party"]


def test_format_body_hashtags():
    # Empty map returns original
    assert format_body_hashtags("Hello world", {}) == "Hello world"

    # Single replacement
    tag_map = {"美股": "美股"}
    assert format_body_hashtags("分析 #美股 走势", tag_map) == "分析 #美股[话题]# 走势"

    # Multiple replacements with prefix collision prevention (#美股 vs #美股大跌)
    tag_map_multi = {"美股": "美股", "美股大跌": "美股大跌"}
    result = format_body_hashtags("今日盘点 #美股 #美股大跌 发生", tag_map_multi)
    assert result == "今日盘点 #美股[话题]# #美股大跌[话题]# 发生"

    # URL fragment should NOT be formatted
    sample = "Link https://site.com#section here #test"
    mapping = {"section": "section", "test": "test"}
    assert format_body_hashtags(sample, mapping) == "Link https://site.com#section here #test[话题]#"

    # Start of line and end of string
    assert (
        format_body_hashtags("#tag at start and #end", {"tag": "tag", "end": "end"})
        == "#tag[话题]# at start and #end[话题]#"
    )


def test_native_hashtags_are_not_formatted_twice():
    body = "正文 #旅行[话题]# #美食"
    assert extract_hashtags(body) == ["旅行", "美食"]
    formatted = format_body_hashtags(body, {"旅行": "旅行", "美食": "美食"})
    assert formatted == "正文 #旅行[话题]# #美食[话题]#"
    assert format_body_hashtags(formatted, {"旅行": "旅行", "美食": "美食"}) == formatted
    assert format_body_hashtags("#旅行[话题]#", {"旅行": "旅行日记"}) == "#旅行日记[话题]#"


def test_format_only_complete_resolved_tokens():
    assert format_body_hashtags("#美股大跌 #未知 #美股", {"美股": "股票"}) == "#美股大跌 #未知 #股票[话题]#"
    assert format_body_hashtags("#raw", {"raw": r"name\1"}) == "#name\\1[话题]#"
    assert format_body_hashtags("#旅行#", {"旅行": "旅行"}) == "#旅行[话题]#"


@pytest.mark.parametrize("command", ["post", "post-video"])
@pytest.mark.parametrize("tag", ["#旅行", "#旅行[话题]#"])
def test_publish_formats_body_and_attaches_only_resolved_topics(command, tag, tmp_path, monkeypatch):
    media = tmp_path / ("image.jpg" if command == "post" else "video.mp4")
    media.write_bytes(b"mock media, never uploaded")
    calls = []
    captured = {}

    class FakeClient:
        def get_upload_permit(self):
            return {"fileId": "media", "token": "fake"}

        get_video_upload_permit = get_upload_permit

        def upload_file(self, *args):
            pass

        upload_video = upload_file

        def search_topics(self, name):
            calls.append(name)
            if name == "旅行":
                return {"topic_info_dtos": [{"id": "topic-id", "name": "旅行日记"}]}
            if name == "无ID":
                return {"topic_info_dtos": [{"name": "无ID"}]}
            return {"topic_info_dtos": []}

        def create_image_note(self, **kwargs):
            captured.update(kwargs)
            return {"note_id": "fake-note"}

        create_video_note = create_image_note

    monkeypatch.setattr("xhs_cli.commands._common.run_client_action", lambda ctx, action: action(FakeClient()))
    flag = "--images" if command == "post" else "--video"
    result = CliRunner().invoke(cli, [
        command, "--title", "test", "--body", f"{tag} #未知 #无ID https://example.com#旅行",
        flag, str(media), "--topic", "旅行", "--json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True
    assert calls == ["旅行", "未知", "无ID"]
    assert captured["desc"] == "#旅行日记[话题]# #未知 #无ID https://example.com#旅行"
    assert captured["topics"] == [{"id": "topic-id", "name": "旅行日记", "type": "topic"}]

