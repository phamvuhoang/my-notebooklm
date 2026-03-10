from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from theflow.settings import settings as flowsettings

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME_TYPE = "application/vnd.google-apps.presentation"

WORKSPACE_MIME_TYPES = {
    GOOGLE_DOC_MIME_TYPE,
    GOOGLE_SHEET_MIME_TYPE,
    GOOGLE_SLIDE_MIME_TYPE,
}

DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
)

DEFAULT_FILE_FIELDS = (
    "id,name,mimeType,modifiedTime,parents,version,md5Checksum,trashed,"
    "webViewLink,owners(displayName,emailAddress),capabilities/canDownload"
)

DEFAULT_CHANGE_FIELDS = (
    "nextPageToken,newStartPageToken,"
    "changes(fileId,removed,file("
    + DEFAULT_FILE_FIELDS
    + "))"
)

WORKSPACE_EXPORT_PRIORITY = {
    GOOGLE_DOC_MIME_TYPE: (
        ("application/pdf", ".pdf"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
        ),
    ),
    GOOGLE_SHEET_MIME_TYPE: (
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        ),
        ("application/pdf", ".pdf"),
    ),
    GOOGLE_SLIDE_MIME_TYPE: (
        ("application/pdf", ".pdf"),
        (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pptx",
        ),
    ),
}


@dataclass(frozen=True)
class GoogleDriveConnectorConfig:
    enabled: bool
    oauth_client_id: str
    oauth_client_secret: str
    oauth_redirect_uri: str
    service_account_file: str
    service_account_info_json: str
    service_account_subject: str
    encryption_key_path: Path
    scopes: tuple[str, ...]
    folder_page_size: int

    @property
    def has_oauth(self) -> bool:
        return bool(self.oauth_client_id and self.oauth_client_secret)

    @property
    def has_service_account(self) -> bool:
        return bool(self.service_account_file or self.service_account_info_json)

    @property
    def auth_modes(self) -> list[tuple[str, str]]:
        modes: list[tuple[str, str]] = []
        if self.has_oauth:
            modes.append(("Connect My Drive", "oauth"))
        if self.has_service_account:
            modes.append(("Use Service Account", "service_account"))
        return modes

    @property
    def is_available(self) -> bool:
        return self.enabled and bool(self.auth_modes)

    def load_service_account_info(self) -> dict:
        if self.service_account_info_json:
            return json.loads(self.service_account_info_json)
        if self.service_account_file:
            return json.loads(Path(self.service_account_file).read_text())
        raise ValueError("Google Drive service account is not configured")


@lru_cache(maxsize=1)
def get_google_drive_config() -> GoogleDriveConnectorConfig:
    app_data_dir = Path(getattr(flowsettings, "KH_APP_DATA_DIR", Path.cwd()))
    return GoogleDriveConnectorConfig(
        enabled=bool(getattr(flowsettings, "KH_GOOGLE_DRIVE_ENABLED", True)),
        oauth_client_id=str(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_OAUTH_CLIENT_ID", "")
        ),
        oauth_client_secret=str(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET", "")
        ),
        oauth_redirect_uri=str(
            getattr(
                flowsettings,
                "KH_GOOGLE_DRIVE_OAUTH_REDIRECT_URI",
                "http://127.0.0.1:8765/google-drive/callback",
            )
        ),
        service_account_file=str(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "")
        ),
        service_account_info_json=str(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "")
        ),
        service_account_subject=str(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_SERVICE_ACCOUNT_SUBJECT", "")
        ),
        encryption_key_path=Path(
            getattr(
                flowsettings,
                "KH_GOOGLE_DRIVE_MASTER_KEY_PATH",
                app_data_dir / "google_drive.key",
            )
        ),
        scopes=tuple(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_SCOPES", DEFAULT_SCOPES)
        ),
        folder_page_size=int(
            getattr(flowsettings, "KH_GOOGLE_DRIVE_FOLDER_PAGE_SIZE", 1000)
        ),
    )
