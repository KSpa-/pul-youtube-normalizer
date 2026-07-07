import pytest
from google.auth.exceptions import RefreshError

import pul_normalizer.auth as auth


class StubCreds:
    def __init__(self, valid=False, expired=True, refresh_token="rt",
                 fail_refresh=False):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self._fail_refresh = fail_refresh

    def refresh(self, request):
        if self._fail_refresh:
            raise RefreshError("token revoked or expired")
        self.valid = True
        self.expired = False

    def to_json(self):
        return '{"stub": true}'


class StubFlow:
    def __init__(self, creds):
        self._creds = creds

    def run_local_server(self, **kwargs):
        return self._creds


def test_token_path_is_anchored_to_project_root():
    assert auth.TOKEN_PATH.is_absolute()


def test_valid_token_is_returned_without_flow(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    good = StubCreds(valid=True, expired=False)
    monkeypatch.setattr(auth.Credentials, "from_authorized_user_file",
                        staticmethod(lambda *a, **k: good))
    assert auth.get_credentials(token_path=token_path) is good


def test_refresh_failure_falls_back_to_interactive_flow(tmp_path, monkeypatch):
    # A revoked/expired refresh token must trigger re-auth, not crash the run.
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    stale = StubCreds(fail_refresh=True)
    fresh = StubCreds(valid=True, expired=False)
    monkeypatch.setattr(auth.Credentials, "from_authorized_user_file",
                        staticmethod(lambda *a, **k: stale))
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file",
                        staticmethod(lambda *a, **k: StubFlow(fresh)))
    monkeypatch.setattr(auth, "_find_client_secrets", lambda: tmp_path / "cs.json")

    creds = auth.get_credentials(token_path=token_path)

    assert creds is fresh
    assert token_path.read_text(encoding="utf-8") == '{"stub": true}'
