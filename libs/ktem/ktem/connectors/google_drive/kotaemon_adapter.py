from __future__ import annotations

import tempfile
from pathlib import Path

from ktem.db.engine import engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from .drive_client import DriveFile
from .export import ExportedDriveArtifact


class KotaemonIndexAdapter:
    def __init__(self, index, settings: dict, user_id: str):
        self._index = index
        self._settings = settings
        self._user_id = user_id

    def count_sources(self) -> int:
        Source = self._index._resources["Source"]
        with Session(engine) as session:
            stmt = select(Source)
            if self._index.config.get("private", False):
                stmt = stmt.where(Source.user == self._user_id)
            return len(session.execute(stmt).all())

    def _name_exists(self, source_name: str, existing_source_id: str | None) -> bool:
        Source = self._index._resources["Source"]
        with Session(engine) as session:
            stmt = select(Source).where(Source.name == source_name)
            if self._index.config.get("private", False):
                stmt = stmt.where(Source.user == self._user_id)
            rows = session.execute(stmt).all()
            for (source,) in rows:
                if existing_source_id and source.id == existing_source_id:
                    continue
                return True
        return False

    def make_source_name(
        self,
        display_name: str,
        drive_file_id: str,
        existing_source_id: str | None = None,
    ) -> str:
        candidate = display_name
        if not self._name_exists(candidate, existing_source_id):
            return candidate
        path = Path(display_name)
        suffix = f" [drive {drive_file_id[:8]}]"
        return f"{path.stem}{suffix}{path.suffix}"

    def upsert_artifact(
        self,
        drive_file: DriveFile,
        artifact: ExportedDriveArtifact,
        source_note: dict,
        existing_source_id: str | None = None,
    ) -> tuple[str, str]:
        source_name = self.make_source_name(
            f"{drive_file.name}{artifact.extension}"
            if not Path(drive_file.name).suffix
            else drive_file.name,
            drive_file.id,
            existing_source_id=existing_source_id,
        )
        indexing_pipeline = self._index.get_indexing_pipeline(
            self._settings, self._user_id
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_path = Path(tmp_dir) / f"{artifact.file_name}{artifact.extension}"
            artifact_path.write_bytes(artifact.content)
            pipeline = indexing_pipeline.route(artifact_path)
            generator = pipeline.stream(
                artifact_path,
                reindex=existing_source_id is not None,
                existing_source_id=existing_source_id,
                source_name=source_name,
                source_note=source_note,
                metadata_overrides={
                    "file_name": source_name,
                    "source_type": "google_drive",
                    "source_label": "Google Drive",
                    "drive_file_id": drive_file.id,
                    "web_view_link": drive_file.web_view_link,
                },
            )
            try:
                while True:
                    next(generator)
            except StopIteration as stop:
                file_id, _ = stop.value

        return file_id, source_name

    def delete_source(self, source_id: str) -> None:
        self._index.delete_source(source_id)
