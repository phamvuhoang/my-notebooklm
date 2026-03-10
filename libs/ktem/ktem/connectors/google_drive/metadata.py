from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from .config import FOLDER_MIME_TYPE
from .drive_client import DriveFile, GoogleDriveClient

_INVALID_FILENAME = re.compile(r'[\\/:*?"<>|]+')
_FOLDER_URL_PATTERNS = (
    re.compile(r"/folders/([A-Za-z0-9_-]+)"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]+)"),
)


def sanitize_filename(filename: str) -> str:
    cleaned = _INVALID_FILENAME.sub("_", filename).strip()
    return cleaned or "google-drive-file"


def split_supported_file_types(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def extract_folder_ids(selected_ids: list[str], manual_input: str) -> list[str]:
    ids = list(selected_ids)
    for line in manual_input.splitlines():
        value = line.strip()
        if not value:
            continue
        folder_id = None
        for pattern in _FOLDER_URL_PATTERNS:
            match = pattern.search(value)
            if match:
                folder_id = match.group(1)
                break
        ids.append(folder_id or value)
    unique_ids: list[str] = []
    seen = set()
    for folder_id in ids:
        if folder_id not in seen:
            unique_ids.append(folder_id)
            seen.add(folder_id)
    return unique_ids


def summarize_owners(owners: list[dict]) -> list[str]:
    output = []
    for owner in owners:
        display = owner.get("displayName") or owner.get("emailAddress") or "Unknown"
        output.append(display)
    return output


class DriveFolderPathResolver:
    def __init__(self, client: GoogleDriveClient):
        self._client = client
        self._folder_cache: dict[str, DriveFile] = {
            "root": DriveFile(id="root", name="My Drive", mime_type=FOLDER_MIME_TYPE)
        }
        self._path_cache: dict[str, str] = {"root": "My Drive"}

    def prime(self, folders: Iterable[DriveFile]):
        for folder in folders:
            if folder.mime_type == FOLDER_MIME_TYPE:
                self._folder_cache[folder.id] = folder

    def resolve_folder_path(self, folder_id: str) -> str:
        if folder_id in self._path_cache:
            return self._path_cache[folder_id]
        folder = self._folder_cache.get(folder_id)
        if folder is None:
            folder = self._client.get_file(folder_id)
            self._folder_cache[folder_id] = folder
        if not folder.parents:
            path = folder.name
        else:
            parent_path = self.resolve_folder_path(folder.parents[0])
            path = str(Path(parent_path) / folder.name)
        self._path_cache[folder_id] = path
        return path

    def resolve_parent_path(self, item: DriveFile) -> str:
        if not item.parents:
            return "My Drive"
        return self.resolve_folder_path(item.parents[0])

    def is_within_roots(self, item: DriveFile, root_ids: set[str]) -> bool:
        if not root_ids:
            return True
        if item.id in root_ids:
            return True
        to_visit = list(item.parents)
        visited = set()
        while to_visit:
            folder_id = to_visit.pop()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            if folder_id in root_ids:
                return True
            if folder_id == "root":
                continue
            folder = self._folder_cache.get(folder_id)
            if folder is None:
                folder = self._client.get_file(folder_id)
                self._folder_cache[folder_id] = folder
            to_visit.extend(folder.parents)
        return False


def folder_choice_label(folder: DriveFile, resolver: DriveFolderPathResolver) -> str:
    if folder.id == "root":
        return "My Drive"
    return resolver.resolve_folder_path(folder.id)


def build_source_note(
    drive_file: DriveFile,
    folder_path: str,
    export_info: dict,
) -> dict:
    return {
        "source_type": "google_drive",
        "source_label": "Google Drive",
        "drive": {
            "id": drive_file.id,
            "name": drive_file.name,
            "mimeType": drive_file.mime_type,
            "modifiedTime": drive_file.modified_time,
            "version": drive_file.version,
            "checksum": drive_file.md5_checksum,
            "owners": summarize_owners(drive_file.owners),
            "parents": drive_file.parents,
            "folder_path": folder_path,
            "webViewLink": drive_file.web_view_link,
            "export": export_info,
        },
    }
