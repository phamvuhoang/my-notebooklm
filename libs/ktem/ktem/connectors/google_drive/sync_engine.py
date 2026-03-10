from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Optional

from googleapiclient.errors import HttpError

from .drive_client import DriveFile, GoogleDriveClient
from .export import DriveExporter
from .kotaemon_adapter import KotaemonIndexAdapter
from .metadata import DriveFolderPathResolver, build_source_note, split_supported_file_types
from .sync_state import GoogleDriveConnection, GoogleDriveStateStore


@dataclass
class DriveSyncResult:
    mode: str
    indexed: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0
    bookmark_token: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class DriveSyncEngine:
    def __init__(
        self,
        client: GoogleDriveClient,
        exporter: DriveExporter,
        adapter: KotaemonIndexAdapter,
        state_store: GoogleDriveStateStore,
        index_config: dict,
    ):
        self._client = client
        self._exporter = exporter
        self._adapter = adapter
        self._state_store = state_store
        self._index_config = index_config
        self._resolver = DriveFolderPathResolver(client)
        self._supported_types = split_supported_file_types(
            index_config.get("supported_file_types", "")
        )

    def sync(
        self,
        connection: GoogleDriveConnection,
        selected_folder_ids: list[str],
        force_full: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ) -> DriveSyncResult:
        logger = log or (lambda _msg: None)
        if force_full or not connection.bookmark_token:
            result = self._full_sync(connection, selected_folder_ids, logger)
        else:
            try:
                result = self._incremental_sync(connection, selected_folder_ids, logger)
            except HttpError as exc:
                if exc.resp.status != 410:
                    raise
                logger("Drive change token expired; falling back to full sync.")
                result = self._full_sync(connection, selected_folder_ids, logger)

        self._state_store.update_connection(
            connection.id,
            bookmark_token=result.bookmark_token,
            last_sync_status="success" if result.failed == 0 else "partial_failure",
            last_error="\n".join(result.errors[-5:]),
            last_sync_stats=result.to_dict(),
        )
        return result

    def _full_sync(
        self,
        connection: GoogleDriveConnection,
        selected_folder_ids: list[str],
        logger: Callable[[str], None],
    ) -> DriveSyncResult:
        result = DriveSyncResult(mode="full")
        root_ids = set(selected_folder_ids)
        existing_mappings = {
            mapping.drive_file_id: mapping
            for mapping in self._state_store.list_mappings(connection.id)
        }
        seen_ids = set()

        for root_id in selected_folder_ids:
            for drive_file in self._crawl_root(root_id):
                seen_ids.add(drive_file.id)
                self._upsert_drive_file(
                    connection,
                    drive_file,
                    existing_mappings,
                    result,
                    logger,
                )

        for drive_file_id, mapping in existing_mappings.items():
            if drive_file_id in seen_ids:
                continue
            logger(f"Removing file no longer present in selected Drive roots: {mapping.source_name}")
            self._adapter.delete_source(mapping.source_id)
            self._state_store.delete_mapping(connection.id, drive_file_id)
            result.deleted += 1

        result.bookmark_token = self._client.get_start_page_token()
        return result

    def _incremental_sync(
        self,
        connection: GoogleDriveConnection,
        selected_folder_ids: list[str],
        logger: Callable[[str], None],
    ) -> DriveSyncResult:
        result = DriveSyncResult(mode="incremental")
        root_ids = set(selected_folder_ids)
        existing_mappings = {
            mapping.drive_file_id: mapping
            for mapping in self._state_store.list_mappings(connection.id)
        }
        changes, next_token = self._client.list_changes(connection.bookmark_token)
        for change in changes:
            drive_file_id = change.get("fileId")
            mapping = existing_mappings.get(drive_file_id)
            if change.get("removed"):
                if mapping:
                    logger(f"Removing deleted Drive file: {mapping.source_name}")
                    self._adapter.delete_source(mapping.source_id)
                    self._state_store.delete_mapping(connection.id, drive_file_id)
                    result.deleted += 1
                else:
                    result.skipped += 1
                continue

            file_payload = change.get("file")
            if not file_payload:
                result.skipped += 1
                continue
            drive_file = self._client.to_drive_file(file_payload)
            if drive_file.is_folder:
                result.skipped += 1
                continue
            if drive_file.trashed:
                if mapping:
                    logger(f"Removing trashed Drive file: {mapping.source_name}")
                    self._adapter.delete_source(mapping.source_id)
                    self._state_store.delete_mapping(connection.id, drive_file.id)
                    result.deleted += 1
                else:
                    result.skipped += 1
                continue

            if not self._resolver.is_within_roots(drive_file, root_ids):
                if mapping:
                    logger(f"Removing Drive file moved out of scope: {mapping.source_name}")
                    self._adapter.delete_source(mapping.source_id)
                    self._state_store.delete_mapping(connection.id, drive_file.id)
                    result.deleted += 1
                else:
                    result.skipped += 1
                continue

            self._upsert_drive_file(
                connection,
                drive_file,
                existing_mappings,
                result,
                logger,
            )

        result.bookmark_token = next_token
        return result

    def _crawl_root(self, root_id: str) -> Iterable[DriveFile]:
        queue = [root_id]
        while queue:
            folder_id = queue.pop(0)
            children = self._client.list_folder_children(folder_id)
            self._resolver.prime(children)
            for child in children:
                if child.is_folder:
                    queue.append(child.id)
                elif not child.trashed:
                    yield child

    def _upsert_drive_file(
        self,
        connection: GoogleDriveConnection,
        drive_file: DriveFile,
        existing_mappings: dict,
        result: DriveSyncResult,
        logger: Callable[[str], None],
    ):
        mapping = existing_mappings.get(drive_file.id)
        folder_path = self._resolver.resolve_parent_path(drive_file)

        if mapping and self._is_unchanged(mapping, drive_file, folder_path):
            result.skipped += 1
            return

        if not mapping:
            max_files = self._index_config.get("max_number_of_files", 0)
            if max_files and self._adapter.count_sources() >= max_files:
                result.failed += 1
                result.errors.append(
                    "Maximum number of indexed files would be exceeded"
                )
                return

        try:
            logger(f"Syncing Google Drive file: {drive_file.name}")
            artifact = self._exporter.export(drive_file, self._supported_types)
            max_file_size = self._index_config.get("max_file_size", 0)
            if max_file_size and len(artifact.content) > max_file_size * 1_000_000:
                raise ValueError(
                    f"Google Drive file '{drive_file.name}' exceeds max file size"
                )
            note = build_source_note(drive_file, folder_path, artifact.export_info)
            source_id, source_name = self._adapter.upsert_artifact(
                drive_file,
                artifact,
                source_note=note,
                existing_source_id=mapping.source_id if mapping else None,
            )
            self._state_store.upsert_mapping(
                connection.id,
                drive_file_id=drive_file.id,
                source_id=source_id,
                source_name=source_name,
                mime_type=drive_file.mime_type,
                modified_time=drive_file.modified_time,
                checksum=drive_file.content_fingerprint,
                folder_path=folder_path,
                metadata=note["drive"],
            )
            if mapping:
                result.updated += 1
            else:
                result.indexed += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append(str(exc))
            logger(f"Failed to sync {drive_file.name}: {exc}")

    def _is_unchanged(self, mapping, drive_file: DriveFile, folder_path: str) -> bool:
        return (
            mapping.checksum == drive_file.content_fingerprint
            and mapping.modified_time == drive_file.modified_time
            and mapping.mime_type == drive_file.mime_type
            and mapping.folder_path == folder_path
            and mapping.file_metadata.get("name") == drive_file.name
        )
