from __future__ import annotations

import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from googleapiclient.errors import HttpError
from openpyxl import Workbook

from .config import (
    GOOGLE_DOC_MIME_TYPE,
    GOOGLE_SHEET_MIME_TYPE,
    GOOGLE_SLIDE_MIME_TYPE,
    WORKSPACE_EXPORT_PRIORITY,
)
from .drive_client import DriveFile, GoogleDriveClient
from .metadata import sanitize_filename


@dataclass(frozen=True)
class ExportedDriveArtifact:
    file_name: str
    extension: str
    mime_type: str
    content: bytes
    export_info: dict


def _is_export_size_error(exc: Exception) -> bool:
    if not isinstance(exc, HttpError):
        return False
    try:
        return b"exportSizeLimitExceeded" in exc.content
    except Exception:
        return False


class DriveExporter:
    def __init__(self, client: GoogleDriveClient):
        self._client = client

    def export(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        if not drive_file.can_download:
            raise ValueError(f"Google Drive file '{drive_file.name}' cannot be downloaded")

        if drive_file.mime_type in WORKSPACE_EXPORT_PRIORITY:
            return self._export_workspace(drive_file, supported_types)
        return self._download_blob(drive_file, supported_types)

    def _download_blob(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        extension = Path(drive_file.name).suffix.lower()
        if not extension:
            extension = mimetypes.guess_extension(drive_file.mime_type) or ".bin"
        if supported_types and extension.lower() not in supported_types:
            raise ValueError(
                f"Unsupported Drive file type '{extension}' for '{drive_file.name}'"
            )
        content = self._client.download_blob(drive_file.id)
        return ExportedDriveArtifact(
            file_name=sanitize_filename(Path(drive_file.name).stem),
            extension=extension.lower(),
            mime_type=drive_file.mime_type,
            content=content,
            export_info={
                "mode": "download",
                "artifactMimeType": drive_file.mime_type,
                "artifactExtension": extension.lower(),
            },
        )

    def _export_workspace(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        for export_mime, extension in WORKSPACE_EXPORT_PRIORITY[drive_file.mime_type]:
            if supported_types and extension not in supported_types:
                continue
            try:
                content = self._client.export_file(drive_file.id, export_mime)
                return ExportedDriveArtifact(
                    file_name=sanitize_filename(Path(drive_file.name).stem),
                    extension=extension,
                    mime_type=export_mime,
                    content=content,
                    export_info={
                        "mode": "export",
                        "artifactMimeType": export_mime,
                        "artifactExtension": extension,
                    },
                )
            except Exception as exc:
                if not _is_export_size_error(exc):
                    raise
                return self._fallback_export(drive_file, supported_types)

        return self._fallback_export(drive_file, supported_types)

    def _fallback_export(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        if drive_file.mime_type == GOOGLE_DOC_MIME_TYPE:
            return self._fallback_doc(drive_file, supported_types)
        if drive_file.mime_type == GOOGLE_SHEET_MIME_TYPE:
            return self._fallback_sheet(drive_file, supported_types)
        if drive_file.mime_type == GOOGLE_SLIDE_MIME_TYPE:
            return self._fallback_slide(drive_file, supported_types)
        raise ValueError(f"Unsupported Google Workspace file '{drive_file.name}'")

    def _fallback_doc(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        extension = ".md" if not supported_types or ".md" in supported_types else ".txt"
        if supported_types and extension not in supported_types:
            raise ValueError(f"No supported export format for '{drive_file.name}'")
        document = self._client.get_doc_content(drive_file.id)
        parts = []
        for block in document.get("body", {}).get("content", []):
            paragraph = block.get("paragraph", {})
            texts = []
            for element in paragraph.get("elements", []):
                text_run = element.get("textRun", {})
                if text_run.get("content"):
                    texts.append(text_run["content"])
            if texts:
                parts.append("".join(texts).rstrip())
        content = "\n\n".join(parts).encode("utf-8")
        return ExportedDriveArtifact(
            file_name=sanitize_filename(Path(drive_file.name).stem),
            extension=extension,
            mime_type="text/markdown" if extension == ".md" else "text/plain",
            content=content,
            export_info={
                "mode": "fallback_docs_api",
                "artifactMimeType": "text/markdown"
                if extension == ".md"
                else "text/plain",
                "artifactExtension": extension,
            },
        )

    def _fallback_sheet(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        spreadsheet = self._client.get_sheet(drive_file.id)
        if not supported_types or ".xlsx" in supported_types:
            workbook = Workbook()
            first = True
            for sheet in spreadsheet.get("sheets", []):
                title = sheet.get("properties", {}).get("title", "Sheet")
                values = self._client.get_sheet_values(drive_file.id, title)
                worksheet = workbook.active if first else workbook.create_sheet()
                worksheet.title = title[:31]
                first = False
                for row in values:
                    worksheet.append(row)
            buffer = io.BytesIO()
            workbook.save(buffer)
            return ExportedDriveArtifact(
                file_name=sanitize_filename(Path(drive_file.name).stem),
                extension=".xlsx",
                mime_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                content=buffer.getvalue(),
                export_info={
                    "mode": "fallback_sheets_api",
                    "artifactMimeType": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                    "artifactExtension": ".xlsx",
                },
            )

        if supported_types and ".txt" not in supported_types:
            raise ValueError(f"No supported export format for '{drive_file.name}'")

        output = []
        for sheet in spreadsheet.get("sheets", []):
            title = sheet.get("properties", {}).get("title", "Sheet")
            values = self._client.get_sheet_values(drive_file.id, title)
            output.append(f"# {title}")
            for row in values:
                output.append("\t".join(str(cell) for cell in row))
            output.append("")
        return ExportedDriveArtifact(
            file_name=sanitize_filename(Path(drive_file.name).stem),
            extension=".txt",
            mime_type="text/plain",
            content="\n".join(output).encode("utf-8"),
            export_info={
                "mode": "fallback_sheets_api",
                "artifactMimeType": "text/plain",
                "artifactExtension": ".txt",
            },
        )

    def _fallback_slide(
        self,
        drive_file: DriveFile,
        supported_types: set[str],
    ) -> ExportedDriveArtifact:
        extension = ".md" if not supported_types or ".md" in supported_types else ".txt"
        if supported_types and extension not in supported_types:
            raise ValueError(f"No supported export format for '{drive_file.name}'")
        presentation = self._client.get_presentation(drive_file.id)
        lines = []
        for idx, slide in enumerate(presentation.get("slides", []), start=1):
            lines.append(f"## Slide {idx}")
            for element in slide.get("pageElements", []):
                shape = element.get("shape", {})
                text = shape.get("text", {})
                paragraphs = []
                for item in text.get("textElements", []):
                    text_run = item.get("textRun", {})
                    if text_run.get("content"):
                        paragraphs.append(text_run["content"].rstrip())
                if paragraphs:
                    lines.append(" ".join(paragraphs))
            lines.append("")
        return ExportedDriveArtifact(
            file_name=sanitize_filename(Path(drive_file.name).stem),
            extension=extension,
            mime_type="text/markdown" if extension == ".md" else "text/plain",
            content="\n".join(lines).encode("utf-8"),
            export_info={
                "mode": "fallback_slides_api",
                "artifactMimeType": "text/markdown"
                if extension == ".md"
                else "text/plain",
                "artifactExtension": extension,
            },
        )
