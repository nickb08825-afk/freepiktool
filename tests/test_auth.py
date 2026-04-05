"""Tests for freepiktool.auth."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from freepiktool.auth import get_credentials, create_session


class TestGetCredentials(unittest.TestCase):
    def test_explicit_args(self):
        email, pw = get_credentials("a@b.com", "secret", interactive=False)
        self.assertEqual(email, "a@b.com")
        self.assertEqual(pw, "secret")

    def test_env_vars(self):
        with patch.dict(os.environ, {"FREEPIK_EMAIL": "env@b.com", "FREEPIK_PASSWORD": "envpw"}):
            email, pw = get_credentials(interactive=False)
        self.assertEqual(email, "env@b.com")
        self.assertEqual(pw, "envpw")

    def test_explicit_overrides_env(self):
        with patch.dict(os.environ, {"FREEPIK_EMAIL": "env@b.com", "FREEPIK_PASSWORD": "envpw"}):
            email, pw = get_credentials("explicit@b.com", "explicitpw", interactive=False)
        self.assertEqual(email, "explicit@b.com")
        self.assertEqual(pw, "explicitpw")

    def test_missing_raises_without_interactive(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                get_credentials(interactive=False)

    def test_interactive_prompt_called_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("freepiktool.auth._prompt_credentials", return_value=("p@b.com", "pw")) as mock_prompt:
                email, pw = get_credentials(interactive=True)
        mock_prompt.assert_called_once()
        self.assertEqual(email, "p@b.com")
        self.assertEqual(pw, "pw")


class TestCreateSession(unittest.TestCase):
    def _make_login_resp(self, status=200, json_body=None):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = json_body or {"success": True}
        resp.raise_for_status = MagicMock()
        return resp

    def test_successful_login(self):
        with patch("freepiktool.auth.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            # GET login page → 200
            page_resp = MagicMock()
            page_resp.raise_for_status = MagicMock()
            # POST credentials → 200 success
            login_resp = self._make_login_resp(200, {"success": True})
            mock_session.get.return_value = page_resp
            mock_session.post.return_value = login_resp

            session = create_session("u@b.com", "pw", interactive=False)
            self.assertIs(session, mock_session)

    def test_login_http_error_raises(self):
        with patch("freepiktool.auth.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            page_resp = MagicMock()
            page_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = page_resp
            # POST → 401
            bad_resp = self._make_login_resp(401, {})
            bad_resp.text = "Unauthorized"
            mock_session.post.return_value = bad_resp

            with self.assertRaises(RuntimeError):
                create_session("u@b.com", "wrong", interactive=False)

    def test_login_api_error_raises(self):
        with patch("freepiktool.auth.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            page_resp = MagicMock()
            page_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = page_resp
            # POST → 200 but with an error in the JSON body
            error_resp = self._make_login_resp(200, {"success": False, "error": "Bad credentials"})
            mock_session.post.return_value = error_resp

            with self.assertRaises(RuntimeError) as ctx:
                create_session("u@b.com", "wrong", interactive=False)
            self.assertIn("Bad credentials", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
