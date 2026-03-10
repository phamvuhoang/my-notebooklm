from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from cryptography.fernet import Fernet
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from requests_oauthlib import OAuth2Session

from .config import GoogleDriveConnectorConfig, get_google_drive_config
from .sync_state import GoogleDriveConnection, GoogleDriveStateStore

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


@dataclass(frozen=True)
class PendingOAuthSession:
    state: str
    code_verifier: str
    redirect_uri: str
    user_id: str
    index_id: int


@dataclass(frozen=True)
class OAuthAuthorizationRequest:
    authorization_url: str
    state: str
    redirect_uri: str


class DriveAuthManager:
    def __init__(
        self,
        state_store: GoogleDriveStateStore,
        config: Optional[GoogleDriveConnectorConfig] = None,
    ):
        self._store = state_store
        self._config = config or get_google_drive_config()

    def _get_cipher(self) -> Fernet:
        key_path = Path(self._config.encryption_key_path)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if not key_path.exists():
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
        return Fernet(key_path.read_bytes())

    def encrypt_payload(self, payload: dict) -> str:
        raw = json.dumps(payload).encode("utf-8")
        return self._get_cipher().encrypt(raw).decode("utf-8")

    def decrypt_payload(self, payload: str) -> dict:
        raw = self._get_cipher().decrypt(payload.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))

    def _normalize_authorized_user_payload(
        self, payload: dict
    ) -> tuple[dict, bool]:
        normalized = dict(payload)
        changed = False

        defaults = {
            "client_id": self._config.oauth_client_id,
            "client_secret": self._config.oauth_client_secret,
            "token_uri": GOOGLE_TOKEN_URL,
        }
        for key, value in defaults.items():
            if value and not normalized.get(key):
                normalized[key] = value
                changed = True

        return normalized, changed

    def begin_oauth(
        self, user_id: str, index_id: int, redirect_uri: Optional[str] = None
    ) -> OAuthAuthorizationRequest:
        if not self._config.has_oauth:
            raise ValueError("Google Drive OAuth is not configured")

        redirect_uri = redirect_uri or self._config.oauth_redirect_uri
        code_verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode()
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("utf-8")).digest()
            )
            .rstrip(b"=")
            .decode("utf-8")
        )
        oauth = OAuth2Session(
            self._config.oauth_client_id,
            scope=list(self._config.scopes),
            redirect_uri=redirect_uri,
        )
        authorization_url, state = oauth.authorization_url(
            GOOGLE_AUTH_URL,
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        self._store.save_pending_oauth(
            user_id=user_id,
            index_id=index_id,
            state=state,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
        return OAuthAuthorizationRequest(
            authorization_url=authorization_url,
            state=state,
            redirect_uri=redirect_uri,
        )

    def complete_oauth(
        self,
        user_id: str,
        index_id: int,
        state: str,
        callback_input: str,
    ) -> GoogleDriveConnection:
        pending_record = self._store.get_pending_oauth(state)
        pending = (
            PendingOAuthSession(
                state=pending_record.state,
                code_verifier=pending_record.code_verifier,
                redirect_uri=pending_record.redirect_uri,
                user_id=pending_record.user,
                index_id=pending_record.index_id,
            )
            if pending_record
            else None
        )
        if pending is None:
            raise ValueError("Google Drive authorization session expired")
        if pending.user_id != user_id or pending.index_id != index_id:
            raise ValueError("Google Drive authorization session does not match")

        code, returned_state = self._parse_callback_input(callback_input)
        if returned_state and returned_state != state:
            raise ValueError("Google Drive authorization state mismatch")

        token_response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self._config.oauth_client_id,
                "client_secret": self._config.oauth_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": pending.redirect_uri,
                "code_verifier": pending.code_verifier,
            },
            timeout=30,
        )
        try:
            token_response.raise_for_status()
        except requests.HTTPError as exc:
            raise ValueError(
                f"Failed to complete Google Drive authorization: {token_response.text}"
            ) from exc

        token_payload, _ = self._normalize_authorized_user_payload(
            token_response.json()
        )
        encrypted = self.encrypt_payload(token_payload)
        connection = self._store.save_connection(
            user_id=user_id,
            index_id=index_id,
            auth_mode="oauth",
            credential=encrypted,
        )
        self._store.delete_pending_oauth(state=state)
        return connection

    def get_credentials(self, connection: GoogleDriveConnection):
        if connection.auth_mode == "service_account":
            info = self._config.load_service_account_info()
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=list(self._config.scopes),
            )
            subject = (
                connection.connection_metadata.get("service_account_subject")
                or self._config.service_account_subject
            )
            if subject:
                credentials = credentials.with_subject(subject)
            return credentials

        if not connection.credential:
            raise ValueError("Google Drive OAuth credential is not available")

        payload, normalized = self._normalize_authorized_user_payload(
            self.decrypt_payload(connection.credential)
        )
        credentials = Credentials.from_authorized_user_info(
            payload,
            scopes=list(self._config.scopes),
        )
        if normalized:
            self._store.update_connection(
                connection.id,
                credential=self.encrypt_payload(payload),
            )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            refreshed, _ = self._normalize_authorized_user_payload(
                json.loads(credentials.to_json())
            )
            self._store.update_connection(
                connection.id,
                credential=self.encrypt_payload(refreshed),
            )

        return credentials

    def disconnect(self, connection: GoogleDriveConnection):
        if connection.auth_mode == "oauth" and connection.credential:
            try:
                payload = self.decrypt_payload(connection.credential)
                token = payload.get("refresh_token") or payload.get("access_token")
                if token:
                    requests.post(
                        GOOGLE_REVOKE_URL,
                        data={"token": token},
                        timeout=10,
                    )
            except Exception:
                pass

    def _parse_callback_input(self, callback_input: str) -> tuple[str, str]:
        callback_input = callback_input.strip()
        if not callback_input:
            raise ValueError("Please paste the Google authorization callback URL")

        if callback_input.startswith("http://") or callback_input.startswith("https://"):
            parsed = urlparse(callback_input)
            query = parse_qs(parsed.query)
            if "error" in query:
                raise ValueError(query["error"][0])
            code = query.get("code", [""])[0]
            state = query.get("state", [""])[0]
            if not code:
                raise ValueError("Google callback URL does not include a code")
            return code, state

        return callback_input, ""
