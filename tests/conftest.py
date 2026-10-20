from __future__ import annotations

import os

import pytest

os.environ.setdefault("OUTPUT", "rich")
# Keep the on-disk DM write throttle out of unit tests; the limiter itself is
# exercised in test_limiter.py against a temporary state directory.
os.environ.setdefault("XHS_WRITE_RPM", "0")


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """Unit tests must not modify the installed account's cookies or caches."""
    from xhs_cli import client_mixins, cookies, limiter

    for module in (cookies, client_mixins, limiter):
        monkeypatch.setattr(module, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(cookies, "_TOKEN_CACHE_MEMORY", None)
    monkeypatch.setattr(cookies, "_TOKEN_CACHE_PATH", None)
    monkeypatch.setattr(client_mixins, "_SEARCH_SESSION_CACHE_PATH", None)
    monkeypatch.setattr(client_mixins, "_SEARCH_SESSION_CACHE_LOADED", False)
