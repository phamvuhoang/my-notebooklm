from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from googleapiclient.errors import HttpError

from ktem.connectors.google_drive.auth import DriveAuthManager
from ktem.connectors.google_drive.config import GoogleDriveConnectorConfig
from ktem.connectors.google_drive.drive_client import DriveFile
from ktem.connectors.google_drive.export import DriveExporter, ExportedDriveArtifact
from ktem.connectors.google_drive.sync_engine import DriveSyncEngine
from ktem.connectors.google_drive.sync_state import GoogleDriveConnection


class FakeDriveClient:
    def __init__(self, root_files=None, changes=None):
        self.root_files = root_files or []
        self.changes = changes or []

    def list_folder_children(self, folder_id: str):
        if folder_id == "root":
            return self.root_files
        return []

    def get_start_page_token(self):
        return "token-1"

    def list_changes(self, page_token: str):
        return self.changes, "token-2"

    def get_file(self, file_id: str):
        if file_id == "root":
            return DriveFile(id="root", name="My Drive", mime_type="application/vnd.google-apps.folder")
        raise ValueError(file_id)

    def get_doc_content(self, file_id: str):
        return {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Hello from Docs"}},
                            ]
                        }
                    }
                ]
            }
        }

    def to_drive_file(self, payload: dict):
        return DriveFile(
            id=payload["id"],
            name=payload["name"],
            mime_type=payload["mimeType"],
            modified_time=payload.get("modifiedTime", ""),
            parents=payload.get("parents", []),
            version=payload.get("version", ""),
            md5_checksum=payload.get("md5Checksum", ""),
            trashed=payload.get("trashed", False),
            web_view_link=payload.get("webViewLink", ""),
            owners=payload.get("owners", []),
            can_download=payload.get("capabilities", {}).get("canDownload", True),
        )

    def export_file(self, file_id: str, mime_type: str):
        return f"{file_id}:{mime_type}".encode("utf-8")

    def download_blob(self, file_id: str):
        return b"blob"


class FakeExporter:
    def export(self, drive_file: DriveFile, supported_types: set[str]):
        return ExportedDriveArtifact(
            file_name=drive_file.name,
            extension=".pdf",
            mime_type="application/pdf",
            content=b"artifact",
            export_info={"mode": "export", "artifactExtension": ".pdf"},
        )


class FakeAdapter:
    def __init__(self):
        self.upserts = []
        self.deleted = []
        self.source_count = 0

    def count_sources(self):
        return self.source_count

    def upsert_artifact(self, drive_file, artifact, source_note, existing_source_id=None):
        source_id = existing_source_id or f"source-{drive_file.id}"
        self.upserts.append(
            {
                "drive_file_id": drive_file.id,
                "source_id": source_id,
                "existing_source_id": existing_source_id,
                "source_note": source_note,
            }
        )
        if existing_source_id is None:
            self.source_count += 1
        return source_id, drive_file.name

    def delete_source(self, source_id: str):
        self.deleted.append(source_id)
        self.source_count = max(0, self.source_count - 1)


class FakeStateStore:
    def __init__(self):
        self.mappings = {}
        self.connection_updates = []
        self.pending_oauth = {}
        self.connection = None

    def list_mappings(self, connection_id: int):
        return list(self.mappings.values())

    def save_connection(
        self,
        user_id: str,
        index_id: int,
        auth_mode: str,
        credential: str | None = None,
        selected_folders: dict | None = None,
        bookmark_token: str | None = None,
        metadata: dict | None = None,
    ):
        self.connection = GoogleDriveConnection(
            id=1,
            user=user_id,
            index_id=index_id,
            auth_mode=auth_mode,
            credential=credential or "",
            selected_folders=selected_folders or {"items": []},
            bookmark_token=bookmark_token or "",
            connection_metadata=metadata or {},
        )
        return self.connection

    def save_pending_oauth(
        self,
        user_id: str,
        index_id: int,
        state: str,
        code_verifier: str,
        redirect_uri: str,
    ):
        pending = SimpleNamespace(
            user=user_id,
            index_id=index_id,
            state=state,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
        self.pending_oauth[state] = pending
        return pending

    def get_pending_oauth(self, state: str):
        return self.pending_oauth.get(state)

    def delete_pending_oauth(self, *, state=None, user_id=None, index_id=None):
        if state is not None:
            self.pending_oauth.pop(state, None)
            return
        to_delete = []
        for item_state, pending in self.pending_oauth.items():
            if user_id is not None and pending.user != user_id:
                continue
            if index_id is not None and pending.index_id != index_id:
                continue
            to_delete.append(item_state)
        for item_state in to_delete:
            self.pending_oauth.pop(item_state, None)

    def upsert_mapping(
        self,
        connection_id: int,
        drive_file_id: str,
        source_id: str,
        source_name: str,
        mime_type: str,
        modified_time: str,
        checksum: str,
        folder_path: str,
        metadata: dict | None = None,
    ):
        mapping = SimpleNamespace(
            connection_id=connection_id,
            drive_file_id=drive_file_id,
            source_id=source_id,
            source_name=source_name,
            mime_type=mime_type,
            modified_time=modified_time,
            checksum=checksum,
            folder_path=folder_path,
            file_metadata=metadata or {},
        )
        self.mappings[drive_file_id] = mapping
        return mapping

    def delete_mapping(self, connection_id: int, drive_file_id: str):
        self.mappings.pop(drive_file_id, None)

    def update_connection(self, connection_id: int, **updates):
        self.connection_updates.append((connection_id, updates))


def _make_doc_http_error():
    response = SimpleNamespace(status=403, reason="Forbidden")
    return HttpError(
        response,
        b'{"error":{"errors":[{"reason":"exportSizeLimitExceeded"}]}}',
        uri="https://www.googleapis.com/drive/v3/files/export",
    )


def _drive_file(name="Quarterly Review", file_id="file-1", mime_type="application/vnd.google-apps.document"):
    return DriveFile(
        id=file_id,
        name=name,
        mime_type=mime_type,
        modified_time="2026-03-09T00:00:00Z",
        parents=["root"],
        version="3",
        md5_checksum="",
        web_view_link="https://drive.google.com/file/d/file-1/view",
    )


def test_drive_exporter_prefers_pdf_for_google_docs():
    client = FakeDriveClient()
    exporter = DriveExporter(client)

    artifact = exporter.export(_drive_file(), supported_types={".pdf", ".txt"})

    assert artifact.extension == ".pdf"
    assert artifact.export_info["mode"] == "export"


def test_drive_exporter_falls_back_to_docs_api_on_export_size_limit():
    client = FakeDriveClient()

    def export_raises(*_args, **_kwargs):
        raise _make_doc_http_error()

    client.export_file = export_raises  # type: ignore[method-assign]
    exporter = DriveExporter(client)

    artifact = exporter.export(_drive_file(), supported_types={".md"})

    assert artifact.extension == ".md"
    assert artifact.export_info["mode"] == "fallback_docs_api"
    assert artifact.content.decode("utf-8") == "Hello from Docs"


def test_drive_sync_engine_is_idempotent_for_unchanged_changes():
    drive_file = _drive_file(name="Quarterly Review.pdf", mime_type="application/pdf")
    client = FakeDriveClient(root_files=[drive_file])
    adapter = FakeAdapter()
    store = FakeStateStore()
    engine = DriveSyncEngine(
        client=client,
        exporter=FakeExporter(),
        adapter=adapter,
        state_store=store,
        index_config={"supported_file_types": ".pdf, .txt", "private": True},
    )
    connection = GoogleDriveConnection(
        id=1,
        user="user-1",
        index_id=1,
        auth_mode="oauth",
        bookmark_token="",
    )

    first = engine.sync(connection, selected_folder_ids=["root"], force_full=True)
    assert first.indexed == 1
    assert len(adapter.upserts) == 1

    client.changes = [
        {
            "fileId": drive_file.id,
            "removed": False,
            "file": {
                "id": drive_file.id,
                "name": drive_file.name,
                "mimeType": drive_file.mime_type,
                "modifiedTime": drive_file.modified_time,
                "parents": drive_file.parents,
                "version": drive_file.version,
                "md5Checksum": drive_file.md5_checksum,
                "trashed": False,
                "webViewLink": drive_file.web_view_link,
                "owners": [],
                "capabilities": {"canDownload": True},
            },
        }
    ]
    connection.bookmark_token = "token-1"
    second = engine.sync(connection, selected_folder_ids=["root"])

    assert second.skipped == 1
    assert len(adapter.upserts) == 1


def test_drive_sync_engine_deletes_removed_files():
    drive_file = _drive_file(name="Quarterly Review.pdf", mime_type="application/pdf")
    client = FakeDriveClient()
    adapter = FakeAdapter()
    store = FakeStateStore()
    store.upsert_mapping(
        connection_id=1,
        drive_file_id=drive_file.id,
        source_id="source-file-1",
        source_name=drive_file.name,
        mime_type=drive_file.mime_type,
        modified_time=drive_file.modified_time,
        checksum=drive_file.content_fingerprint,
        folder_path="My Drive",
        metadata={"name": drive_file.name},
    )
    engine = DriveSyncEngine(
        client=client,
        exporter=FakeExporter(),
        adapter=adapter,
        state_store=store,
        index_config={"supported_file_types": ".pdf, .txt", "private": True},
    )
    connection = GoogleDriveConnection(
        id=1,
        user="user-1",
        index_id=1,
        auth_mode="oauth",
        bookmark_token="token-1",
    )
    client.changes = [{"fileId": drive_file.id, "removed": True}]

    result = engine.sync(connection, selected_folder_ids=["root"])

    assert result.deleted == 1
    assert adapter.deleted == ["source-file-1"]
    assert drive_file.id not in store.mappings


def test_drive_auth_manager_encrypts_payload_and_parses_callback(tmp_path):
    key_path = tmp_path / "google-drive.key"
    config = GoogleDriveConnectorConfig(
        enabled=True,
        oauth_client_id="client-id",
        oauth_client_secret="client-secret",
        oauth_redirect_uri="http://127.0.0.1:8765/google-drive/callback",
        service_account_file="",
        service_account_info_json="",
        service_account_subject="",
        encryption_key_path=Path(key_path),
        scopes=("https://www.googleapis.com/auth/drive.readonly",),
        folder_page_size=1000,
    )
    auth = DriveAuthManager(FakeStateStore(), config)

    encrypted = auth.encrypt_payload({"refresh_token": "secret", "token": "value"})
    assert auth.decrypt_payload(encrypted)["refresh_token"] == "secret"
    assert auth._parse_callback_input(
        "http://127.0.0.1:8765/google-drive/callback?code=abc&state=xyz"
    ) == ("abc", "xyz")


def test_drive_auth_manager_persists_pending_oauth_between_instances(tmp_path):
    key_path = tmp_path / "google-drive.key"
    config = GoogleDriveConnectorConfig(
        enabled=True,
        oauth_client_id="client-id",
        oauth_client_secret="client-secret",
        oauth_redirect_uri="http://127.0.0.1:8765/google-drive/callback",
        service_account_file="",
        service_account_info_json="",
        service_account_subject="",
        encryption_key_path=Path(key_path),
        scopes=("https://www.googleapis.com/auth/drive.readonly",),
        folder_page_size=1000,
    )
    store = FakeStateStore()

    with patch(
        "ktem.connectors.google_drive.auth.OAuth2Session.authorization_url",
        return_value=("https://accounts.google.com/o/oauth2/v2/auth?state=state-1", "state-1"),
    ):
        first_auth = DriveAuthManager(store, config)
        request = first_auth.begin_oauth("user-1", 7)

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }

    with patch(
        "ktem.connectors.google_drive.auth.requests.post",
        return_value=DummyResponse(),
    ):
        second_auth = DriveAuthManager(store, config)
        connection = second_auth.complete_oauth(
            "user-1",
            7,
            request.state,
            "http://127.0.0.1:8765/google-drive/callback?code=code-1&state=state-1",
        )

    assert connection.auth_mode == "oauth"
    assert store.get_pending_oauth("state-1") is None
    assert second_auth.decrypt_payload(connection.credential)["refresh_token"] == "refresh-token"
    saved_payload = second_auth.decrypt_payload(connection.credential)
    assert saved_payload["client_id"] == "client-id"
    assert saved_payload["client_secret"] == "client-secret"


def test_drive_auth_manager_backfills_missing_oauth_client_fields(tmp_path):
    key_path = tmp_path / "google-drive.key"
    config = GoogleDriveConnectorConfig(
        enabled=True,
        oauth_client_id="client-id",
        oauth_client_secret="client-secret",
        oauth_redirect_uri="http://127.0.0.1:8765/google-drive/callback",
        service_account_file="",
        service_account_info_json="",
        service_account_subject="",
        encryption_key_path=Path(key_path),
        scopes=("https://www.googleapis.com/auth/drive.readonly",),
        folder_page_size=1000,
    )
    store = FakeStateStore()
    auth = DriveAuthManager(store, config)
    connection = GoogleDriveConnection(
        id=99,
        user="user-1",
        index_id=1,
        auth_mode="oauth",
        credential=auth.encrypt_payload(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "token_type": "Bearer",
                "expiry": "2026-03-10T00:00:00Z",
            }
        ),
    )

    class DummyCredentials:
        expired = False
        refresh_token = "refresh-token"

    captured = {}

    def fake_from_authorized_user_info(info, scopes):
        captured["info"] = info
        captured["scopes"] = scopes
        return DummyCredentials()

    with patch(
        "ktem.connectors.google_drive.auth.Credentials.from_authorized_user_info",
        side_effect=fake_from_authorized_user_info,
    ):
        auth.get_credentials(connection)

    assert captured["info"]["client_id"] == "client-id"
    assert captured["info"]["client_secret"] == "client-secret"
    assert store.connection_updates[-1][0] == 99
