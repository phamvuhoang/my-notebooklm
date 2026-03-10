from __future__ import annotations

from datetime import datetime
from typing import Optional

from ktem.db.engine import engine
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel, Session, select
from tzlocal import get_localzone


def _now():
    return datetime.now(get_localzone())


class GoogleDriveConnection(SQLModel, table=True):
    __tablename__ = "ktem__google_drive_connection"
    __table_args__ = (
        UniqueConstraint("user", "index_id", name="_google_drive_user_index_uc"),
        {"extend_existing": True},
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user: str = Field(index=True)
    index_id: int = Field(index=True)
    auth_mode: str = Field(default="oauth")
    credential: str = Field(default="")
    selected_folders: dict = Field(
        default_factory=lambda: {"items": []},
        sa_column=Column(JSON),
    )
    bookmark_token: str = Field(default="")
    last_sync_status: str = Field(default="")
    last_error: str = Field(default="")
    last_sync_stats: dict = Field(default_factory=dict, sa_column=Column(JSON))
    connection_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    date_created: datetime = Field(default_factory=_now)
    date_updated: datetime = Field(default_factory=_now)


class GoogleDriveFileMap(SQLModel, table=True):
    __tablename__ = "ktem__google_drive_file_map"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "drive_file_id",
            name="_google_drive_connection_file_uc",
        ),
        {"extend_existing": True},
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    connection_id: int = Field(index=True)
    drive_file_id: str = Field(index=True)
    source_id: str = Field(index=True)
    source_name: str = Field(default="")
    mime_type: str = Field(default="")
    modified_time: str = Field(default="")
    checksum: str = Field(default="")
    folder_path: str = Field(default="")
    file_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    date_created: datetime = Field(default_factory=_now)
    date_updated: datetime = Field(default_factory=_now)


class GoogleDrivePendingOAuth(SQLModel, table=True):
    __tablename__ = "ktem__google_drive_pending_oauth"
    __table_args__ = (
        UniqueConstraint("state", name="_google_drive_pending_oauth_state_uc"),
        UniqueConstraint(
            "user",
            "index_id",
            name="_google_drive_pending_oauth_user_index_uc",
        ),
        {"extend_existing": True},
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user: str = Field(index=True)
    index_id: int = Field(index=True)
    state: str = Field(index=True)
    code_verifier: str = Field(default="")
    redirect_uri: str = Field(default="")
    date_created: datetime = Field(default_factory=_now)
    date_updated: datetime = Field(default_factory=_now)


SQLModel.metadata.create_all(
    engine,
    tables=[
        GoogleDriveConnection.__table__,
        GoogleDriveFileMap.__table__,
        GoogleDrivePendingOAuth.__table__,
    ],
)


class GoogleDriveStateStore:
    def get_pending_oauth(self, state: str) -> GoogleDrivePendingOAuth | None:
        with Session(engine) as session:
            stmt = select(GoogleDrivePendingOAuth).where(
                GoogleDrivePendingOAuth.state == state
            )
            return session.exec(stmt).first()

    def save_pending_oauth(
        self,
        user_id: str,
        index_id: int,
        state: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> GoogleDrivePendingOAuth:
        with Session(engine) as session:
            stmt = select(GoogleDrivePendingOAuth).where(
                GoogleDrivePendingOAuth.user == user_id,
                GoogleDrivePendingOAuth.index_id == index_id,
            )
            pending = session.exec(stmt).first()
            if pending is None:
                pending = GoogleDrivePendingOAuth(
                    user=user_id,
                    index_id=index_id,
                    state=state,
                )
                session.add(pending)

            pending.state = state
            pending.code_verifier = code_verifier
            pending.redirect_uri = redirect_uri
            pending.date_updated = _now()
            session.commit()
            session.refresh(pending)
            return pending

    def delete_pending_oauth(
        self,
        *,
        state: Optional[str] = None,
        user_id: Optional[str] = None,
        index_id: Optional[int] = None,
    ) -> None:
        with Session(engine) as session:
            stmt = select(GoogleDrivePendingOAuth)
            if state is not None:
                stmt = stmt.where(GoogleDrivePendingOAuth.state == state)
            if user_id is not None:
                stmt = stmt.where(GoogleDrivePendingOAuth.user == user_id)
            if index_id is not None:
                stmt = stmt.where(GoogleDrivePendingOAuth.index_id == index_id)

            rows = list(session.exec(stmt))
            for row in rows:
                session.delete(row)
            if rows:
                session.commit()

    def get_connection(
        self, user_id: str, index_id: int
    ) -> GoogleDriveConnection | None:
        with Session(engine) as session:
            stmt = select(GoogleDriveConnection).where(
                GoogleDriveConnection.user == user_id,
                GoogleDriveConnection.index_id == index_id,
            )
            return session.exec(stmt).first()

    def save_connection(
        self,
        user_id: str,
        index_id: int,
        auth_mode: str,
        credential: Optional[str] = None,
        selected_folders: Optional[dict] = None,
        bookmark_token: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> GoogleDriveConnection:
        with Session(engine) as session:
            stmt = select(GoogleDriveConnection).where(
                GoogleDriveConnection.user == user_id,
                GoogleDriveConnection.index_id == index_id,
            )
            connection = session.exec(stmt).first()
            if connection is None:
                connection = GoogleDriveConnection(
                    user=user_id,
                    index_id=index_id,
                    auth_mode=auth_mode,
                )
                session.add(connection)

            connection.auth_mode = auth_mode
            if credential is not None:
                connection.credential = credential
            if selected_folders is not None:
                connection.selected_folders = selected_folders
            if bookmark_token is not None:
                connection.bookmark_token = bookmark_token
            if metadata is not None:
                connection.connection_metadata = metadata
            connection.date_updated = _now()
            session.commit()
            session.refresh(connection)
            return connection

    def update_connection(self, connection_id: int, **updates) -> GoogleDriveConnection:
        with Session(engine) as session:
            connection = session.get(GoogleDriveConnection, connection_id)
            if connection is None:
                raise ValueError(f"Google Drive connection {connection_id} not found")

            for key, value in updates.items():
                setattr(connection, key, value)
            connection.date_updated = _now()
            session.add(connection)
            session.commit()
            session.refresh(connection)
            return connection

    def delete_connection(self, user_id: str, index_id: int) -> None:
        with Session(engine) as session:
            stmt = select(GoogleDriveConnection).where(
                GoogleDriveConnection.user == user_id,
                GoogleDriveConnection.index_id == index_id,
            )
            connection = session.exec(stmt).first()
            if connection is None:
                return

            mapping_stmt = select(GoogleDriveFileMap).where(
                GoogleDriveFileMap.connection_id == connection.id
            )
            for mapping in session.exec(mapping_stmt):
                session.delete(mapping)
            session.delete(connection)
            session.commit()

    def get_mapping(
        self, connection_id: int, drive_file_id: str
    ) -> GoogleDriveFileMap | None:
        with Session(engine) as session:
            stmt = select(GoogleDriveFileMap).where(
                GoogleDriveFileMap.connection_id == connection_id,
                GoogleDriveFileMap.drive_file_id == drive_file_id,
            )
            return session.exec(stmt).first()

    def list_mappings(self, connection_id: int) -> list[GoogleDriveFileMap]:
        with Session(engine) as session:
            stmt = select(GoogleDriveFileMap).where(
                GoogleDriveFileMap.connection_id == connection_id
            )
            return list(session.exec(stmt))

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
        metadata: Optional[dict] = None,
    ) -> GoogleDriveFileMap:
        with Session(engine) as session:
            stmt = select(GoogleDriveFileMap).where(
                GoogleDriveFileMap.connection_id == connection_id,
                GoogleDriveFileMap.drive_file_id == drive_file_id,
            )
            mapping = session.exec(stmt).first()
            if mapping is None:
                mapping = GoogleDriveFileMap(
                    connection_id=connection_id,
                    drive_file_id=drive_file_id,
                    source_id=source_id,
                )
                session.add(mapping)

            mapping.source_id = source_id
            mapping.source_name = source_name
            mapping.mime_type = mime_type
            mapping.modified_time = modified_time
            mapping.checksum = checksum
            mapping.folder_path = folder_path
            mapping.file_metadata = metadata or {}
            mapping.date_updated = _now()
            session.commit()
            session.refresh(mapping)
            return mapping

    def delete_mapping(self, connection_id: int, drive_file_id: str) -> None:
        with Session(engine) as session:
            stmt = select(GoogleDriveFileMap).where(
                GoogleDriveFileMap.connection_id == connection_id,
                GoogleDriveFileMap.drive_file_id == drive_file_id,
            )
            mapping = session.exec(stmt).first()
            if mapping is None:
                return
            session.delete(mapping)
            session.commit()

    def delete_mappings_by_source_id(self, source_id: str) -> None:
        with Session(engine) as session:
            stmt = select(GoogleDriveFileMap).where(
                GoogleDriveFileMap.source_id == source_id
            )
            mappings = list(session.exec(stmt))
            for mapping in mappings:
                session.delete(mapping)
            if mappings:
                session.commit()
