from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from .config import DEFAULT_CHANGE_FIELDS, DEFAULT_FILE_FIELDS, FOLDER_MIME_TYPE


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        return exc.resp.status in {403, 429, 500, 502, 503, 504}
    return False


def _retryable():
    return retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=16),
        retry=retry_if_exception(_is_retryable_error),
    )


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str = ""
    parents: list[str] = field(default_factory=list)
    version: str = ""
    md5_checksum: str = ""
    trashed: bool = False
    web_view_link: str = ""
    owners: list[dict] = field(default_factory=list)
    can_download: bool = True

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME_TYPE

    @property
    def content_fingerprint(self) -> str:
        return self.md5_checksum or f"{self.version}:{self.modified_time}"


class GoogleDriveClient:
    def __init__(self, credentials):
        self._credentials = credentials
        self._drive = None
        self._docs = None
        self._sheets = None
        self._slides = None

    @property
    def drive(self):
        if self._drive is None:
            self._drive = build(
                "drive", "v3", credentials=self._credentials, cache_discovery=False
            )
        return self._drive

    @property
    def docs(self):
        if self._docs is None:
            self._docs = build(
                "docs", "v1", credentials=self._credentials, cache_discovery=False
            )
        return self._docs

    @property
    def sheets(self):
        if self._sheets is None:
            self._sheets = build(
                "sheets", "v4", credentials=self._credentials, cache_discovery=False
            )
        return self._sheets

    @property
    def slides(self):
        if self._slides is None:
            self._slides = build(
                "slides", "v1", credentials=self._credentials, cache_discovery=False
            )
        return self._slides

    def to_drive_file(self, payload: dict) -> DriveFile:
        return DriveFile(
            id=payload["id"],
            name=payload["name"],
            mime_type=payload["mimeType"],
            modified_time=payload.get("modifiedTime", ""),
            parents=payload.get("parents", []),
            version=str(payload.get("version", "")),
            md5_checksum=payload.get("md5Checksum", ""),
            trashed=payload.get("trashed", False),
            web_view_link=payload.get("webViewLink", ""),
            owners=payload.get("owners", []),
            can_download=payload.get("capabilities", {}).get("canDownload", True),
        )

    @_retryable()
    def get_file(self, file_id: str, fields: str = DEFAULT_FILE_FIELDS) -> DriveFile:
        payload = (
            self.drive.files()
            .get(
                fileId=file_id,
                fields=fields,
                supportsAllDrives=True,
            )
            .execute()
        )
        return self.to_drive_file(payload)

    @_retryable()
    def list_folder_children(self, folder_id: str) -> list[DriveFile]:
        page_token = None
        results: list[DriveFile] = []
        while True:
            payload = (
                self.drive.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    pageSize=1000,
                    pageToken=page_token,
                    fields=f"nextPageToken,files({DEFAULT_FILE_FIELDS})",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            results.extend(self.to_drive_file(item) for item in payload.get("files", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return results

    @_retryable()
    def list_folders(self, page_size: int = 1000) -> list[DriveFile]:
        page_token = None
        results = [
            DriveFile(id="root", name="My Drive", mime_type=FOLDER_MIME_TYPE)
        ]
        while True:
            payload = (
                self.drive.files()
                .list(
                    q=(
                        "mimeType='application/vnd.google-apps.folder' "
                        "and trashed=false"
                    ),
                    pageSize=page_size,
                    pageToken=page_token,
                    fields=f"nextPageToken,files({DEFAULT_FILE_FIELDS})",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            results.extend(self.to_drive_file(item) for item in payload.get("files", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return results

    @_retryable()
    def download_blob(self, file_id: str) -> bytes:
        import io

        request = self.drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    @_retryable()
    def export_file(self, file_id: str, mime_type: str) -> bytes:
        return self.drive.files().export(fileId=file_id, mimeType=mime_type).execute()

    @_retryable()
    def get_start_page_token(self) -> str:
        payload = self.drive.changes().getStartPageToken().execute()
        return payload["startPageToken"]

    @_retryable()
    def list_changes(self, page_token: str) -> tuple[list[dict], str]:
        current = page_token
        changes: list[dict] = []
        next_start_token = page_token
        while True:
            payload = (
                self.drive.changes()
                .list(
                    pageToken=current,
                    includeRemoved=True,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    fields=DEFAULT_CHANGE_FIELDS,
                )
                .execute()
            )
            changes.extend(payload.get("changes", []))
            next_start_token = payload.get("newStartPageToken", next_start_token)
            current = payload.get("nextPageToken")
            if not current:
                break
        return changes, next_start_token

    @_retryable()
    def get_doc_content(self, file_id: str) -> dict:
        return self.docs.documents().get(documentId=file_id).execute()

    @_retryable()
    def get_sheet(self, file_id: str) -> dict:
        return self.sheets.spreadsheets().get(spreadsheetId=file_id).execute()

    @_retryable()
    def get_sheet_values(self, file_id: str, range_name: str) -> list[list[str]]:
        payload = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=file_id, range=range_name)
            .execute()
        )
        return payload.get("values", [])

    @_retryable()
    def get_presentation(self, file_id: str) -> dict:
        return self.slides.presentations().get(presentationId=file_id).execute()

    def iter_changes(self, page_token: str) -> Iterable[dict]:
        changes, _ = self.list_changes(page_token)
        return iter(changes)
