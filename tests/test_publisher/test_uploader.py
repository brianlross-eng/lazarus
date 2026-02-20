"""Tests for the devpi uploader."""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazarus.publisher.uploader import DevpiUploader, UploadError


class TestDevpiUploaderInit:
    def test_defaults(self):
        u = DevpiUploader(server_url="http://localhost:3141")
        assert u._index == "lazarus/packages"
        assert u._user == "lazarus"
        assert u._token is None
        u.close()

    def test_custom_index(self):
        u = DevpiUploader(
            server_url="http://localhost:3141",
            index="myuser/myindex",
            user="myuser",
            password="secret",
        )
        assert u._index == "myuser/myindex"
        assert u._user == "myuser"
        u.close()

    def test_upload_url(self):
        u = DevpiUploader(server_url="http://localhost:3141")
        assert u._get_upload_url() == "http://localhost:3141/lazarus/packages/"
        u.close()

    def test_strips_trailing_slash(self):
        u = DevpiUploader(server_url="http://localhost:3141/")
        assert u._server_url == "http://localhost:3141"
        u.close()


class TestDevpiLogin:
    def test_login_success(self):
        u = DevpiUploader(
            server_url="http://localhost:3141",
            user="lazarus",
            password="secret",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {"password": "session-token-123", "expiration": 36000},
            "type": "proxyauth",
            "message": "login successful",
        }

        with patch.object(u._http, "post", return_value=mock_resp) as mock_post:
            token = u._login()

        assert token == "session-token-123"
        assert u._token == "session-token-123"
        mock_post.assert_called_once_with(
            "http://localhost:3141/+login",
            json={"user": "lazarus", "password": "secret"},
        )
        u.close()

    def test_login_failure(self):
        u = DevpiUploader(
            server_url="http://localhost:3141",
            user="lazarus",
            password="wrong",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "invalid credentials"

        with patch.object(u._http, "post", return_value=mock_resp):
            with pytest.raises(UploadError, match="Login failed"):
                u._login()
        u.close()

    def test_auth_header_triggers_login(self):
        u = DevpiUploader(
            server_url="http://localhost:3141",
            user="lazarus",
            password="secret",
        )
        assert u._token is None

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {"password": "tok-abc"},
        }

        with patch.object(u._http, "post", return_value=mock_resp):
            header = u._auth_header()

        expected = b64encode(b"lazarus:tok-abc").decode("ascii")
        assert header == {"X-Devpi-Auth": expected}
        u.close()


class TestDevpiUpload:
    def test_upload_success(self, tmp_path: Path):
        # Create fake dist files
        sdist = tmp_path / "pkg-1.0.0.post314.tar.gz"
        sdist.write_bytes(b"fake sdist content")
        wheel = tmp_path / "pkg-1.0.0.post314-py3-none-any.whl"
        wheel.write_bytes(b"fake wheel content")

        u = DevpiUploader(
            server_url="http://localhost:3141",
            user="lazarus",
            password="secret",
        )
        u._token = "preloaded-token"

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(u._http, "post", return_value=mock_resp):
            uploaded = u.upload([sdist, wheel])

        assert uploaded == [sdist.name, wheel.name]
        u.close()

    def test_upload_retries_on_401(self, tmp_path: Path):
        sdist = tmp_path / "pkg-1.0.0.post314.tar.gz"
        sdist.write_bytes(b"fake content")

        u = DevpiUploader(
            server_url="http://localhost:3141",
            user="lazarus",
            password="secret",
        )
        u._token = "expired-token"

        # First call returns 401, login call succeeds, retry succeeds
        resp_401 = MagicMock()
        resp_401.status_code = 401

        resp_login = MagicMock()
        resp_login.status_code = 200
        resp_login.json.return_value = {
            "result": {"password": "new-token"},
        }

        resp_ok = MagicMock()
        resp_ok.status_code = 200

        with patch.object(u._http, "post", side_effect=[resp_401, resp_login, resp_ok]):
            uploaded = u.upload([sdist])

        assert uploaded == [sdist.name]
        assert u._token == "new-token"
        u.close()

    def test_upload_failure_raises(self, tmp_path: Path):
        sdist = tmp_path / "pkg-1.0.0.post314.tar.gz"
        sdist.write_bytes(b"fake content")

        u = DevpiUploader(
            server_url="http://localhost:3141",
            user="lazarus",
            password="secret",
        )
        u._token = "valid-token"

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch.object(u._http, "post", return_value=mock_resp):
            with pytest.raises(UploadError, match="Upload failed"):
                u.upload([sdist])
        u.close()


class TestDevpiCheckExists:
    def test_exists(self):
        u = DevpiUploader(server_url="http://localhost:3141")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<a href="pkg-1.0.0.post314.tar.gz">pkg-1.0.0.post314.tar.gz</a>'

        with patch.object(u._http, "get", return_value=mock_resp):
            assert u.check_exists("pkg", "1.0.0.post314") is True
        u.close()

    def test_not_exists(self):
        u = DevpiUploader(server_url="http://localhost:3141")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<a href="pkg-0.9.0.tar.gz">pkg-0.9.0.tar.gz</a>'

        with patch.object(u._http, "get", return_value=mock_resp):
            assert u.check_exists("pkg", "1.0.0.post314") is False
        u.close()

    def test_404_means_not_exists(self):
        u = DevpiUploader(server_url="http://localhost:3141")

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch.object(u._http, "get", return_value=mock_resp):
            assert u.check_exists("pkg", "1.0.0.post314") is False
        u.close()
