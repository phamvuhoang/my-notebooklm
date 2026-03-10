from __future__ import annotations

import json
import weakref
from typing import Optional

import gradio as gr
from ktem.app import BasePage
from ktem.db.models import User, engine
from sqlmodel import Session, select

from .auth import DriveAuthManager
from .config import get_google_drive_config
from .drive_client import GoogleDriveClient
from .export import DriveExporter
from .kotaemon_adapter import KotaemonIndexAdapter
from .metadata import DriveFolderPathResolver, extract_folder_ids, folder_choice_label
from .sync_engine import DriveSyncEngine
from .sync_state import GoogleDriveStateStore


class GoogleDriveTab(BasePage):
    def __init__(self, app, index, host_page):
        super().__init__(app)
        self._index = index
        self._host_page_ref = weakref.ref(host_page)
        self._config = get_google_drive_config()
        self._store = GoogleDriveStateStore()
        self._auth = DriveAuthManager(self._store, self._config)
        self.on_building_ui()

    def on_building_ui(self):
        self.drive_status = gr.Markdown(self._status_text(None, None))
        self.drive_auth_mode = gr.Radio(
            label="Drive auth mode",
            choices=self._config.auth_modes,
            value=self._config.auth_modes[0][1] if self._config.auth_modes else None,
            interactive=bool(self._config.auth_modes),
        )

        gr.Markdown(
            "Use OAuth to connect your own Google Drive, or a configured service "
            "account for centralized indexing. For OAuth, authorize the app and paste "
            "the full callback URL back here."
        )

        with gr.Row():
            self.drive_connect_button = gr.Button("Connect")
            self.drive_disconnect_button = gr.Button("Disconnect", variant="stop")

        self.drive_auth_link = gr.Markdown("")
        self.drive_oauth_state = gr.State(value="")
        self.drive_oauth_callback = gr.Textbox(
            label="OAuth callback URL",
            placeholder="Paste the full Google OAuth callback URL here",
            lines=2,
        )
        self.drive_complete_oauth_button = gr.Button("Complete OAuth")

        with gr.Row():
            self.drive_refresh_folders_button = gr.Button("Refresh folders")
            self.drive_sync_button = gr.Button("Sync now", variant="primary")
        self.drive_folder_picker = gr.Dropdown(
            label="Google Drive folders",
            multiselect=True,
            choices=[],
            value=[],
        )
        self.drive_manual_folder_ids = gr.Textbox(
            label="Additional folder IDs or URLs",
            placeholder="One folder ID or Google Drive folder URL per line",
            lines=3,
        )
        self.drive_force_full_sync = gr.Checkbox(
            label="Force full sync",
            value=False,
        )
        self.drive_sync_result = gr.Textbox(label="Sync result", lines=3)
        self.drive_sync_logs = gr.Textbox(label="Sync logs", lines=10)

    def on_register_events(self):
        host_page = self._host_page_ref()
        if host_page is None:
            raise RuntimeError("Google Drive tab host page is no longer available")

        self.drive_connect_button.click(
            self.connect_drive,
            inputs=[self._app.user_id, self.drive_auth_mode],
            outputs=[
                self.drive_status,
                self.drive_auth_link,
                self.drive_oauth_state,
                self.drive_sync_result,
                self.drive_sync_logs,
            ],
        )
        self.drive_complete_oauth_button.click(
            self.complete_oauth,
            inputs=[
                self._app.user_id,
                self.drive_oauth_state,
                self.drive_oauth_callback,
            ],
            outputs=[
                self.drive_status,
                self.drive_auth_link,
                self.drive_oauth_state,
                self.drive_oauth_callback,
                self.drive_sync_result,
                self.drive_sync_logs,
            ],
        )
        self.drive_disconnect_button.click(
            self.disconnect_drive,
            inputs=[self._app.user_id],
            outputs=[
                self.drive_status,
                self.drive_auth_link,
                self.drive_oauth_state,
                self.drive_oauth_callback,
                self.drive_folder_picker,
                self.drive_sync_result,
                self.drive_sync_logs,
            ],
        )
        self.drive_refresh_folders_button.click(
            self.refresh_folders,
            inputs=[self._app.user_id],
            outputs=[
                self.drive_status,
                self.drive_folder_picker,
                self.drive_sync_result,
                self.drive_sync_logs,
            ],
        )
        on_sync = self.drive_sync_button.click(
            self.sync_drive,
            inputs=[
                self._app.user_id,
                self._app.settings_state,
                self.drive_folder_picker,
                self.drive_manual_folder_ids,
                self.drive_force_full_sync,
            ],
            outputs=[
                self.drive_status,
                self.drive_folder_picker,
                self.drive_sync_result,
                self.drive_sync_logs,
            ],
        )
        on_sync = on_sync.then(
            host_page.list_file,
            inputs=[self._app.user_id, host_page.filter],
            outputs=[host_page.file_list_state, host_page.file_list],
        ).then(
            host_page.list_group,
            inputs=[self._app.user_id, host_page.file_list_state],
            outputs=[host_page.group_list_state, host_page.group_list],
        ).then(
            host_page.list_file_names,
            inputs=[host_page.file_list_state],
            outputs=[host_page.group_files],
        )
        for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
            on_sync = on_sync.then(**event)

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name=f"onFileIndex{self._index.id}Changed",
            definition={
                "fn": self.load_state,
                "inputs": [self._app.user_id],
                "outputs": [
                    self.drive_status,
                    self.drive_folder_picker,
                    self.drive_auth_link,
                    self.drive_oauth_state,
                    self.drive_oauth_callback,
                    self.drive_sync_result,
                    self.drive_sync_logs,
                ],
                "show_progress": "hidden",
            },
        )
        if self._app.f_user_management:
            for event_name in ["onSignIn", "onSignOut"]:
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_state,
                        "inputs": [self._app.user_id],
                        "outputs": [
                            self.drive_status,
                            self.drive_folder_picker,
                            self.drive_auth_link,
                            self.drive_oauth_state,
                            self.drive_oauth_callback,
                            self.drive_sync_result,
                            self.drive_sync_logs,
                        ],
                        "show_progress": "hidden",
                    },
                )

    def _on_app_created(self):
        self._app.app.load(
            self.load_state,
            inputs=[self._app.user_id],
            outputs=[
                self.drive_status,
                self.drive_folder_picker,
                self.drive_auth_link,
                self.drive_oauth_state,
                self.drive_oauth_callback,
                self.drive_sync_result,
                self.drive_sync_logs,
            ],
        )

    def _get_connection(self, user_id: Optional[str]):
        if user_id is None:
            return None
        return self._store.get_connection(str(user_id), self._index.id)

    def _is_admin(self, user_id: Optional[str]) -> bool:
        if not self._app.f_user_management or user_id is None:
            return True
        with Session(engine) as session:
            stmt = select(User).where(User.id == user_id)
            user = session.exec(stmt).first()
            return bool(user and user.admin)

    def _status_text(self, user_id: Optional[str], connection) -> str:
        if not self._config.enabled:
            return "Google Drive is disabled in the application configuration."
        if not self._config.auth_modes:
            return (
                "Google Drive is not configured. Set OAuth or service-account "
                "credentials before using this knowledge source."
            )
        if user_id is None:
            return "Sign in to connect a Google Drive knowledge source."
        if connection is None:
            return "Google Drive is not connected for this collection."

        folder_items = connection.selected_folders.get("items", [])
        folder_lines = ", ".join(item.get("label", item["id"]) for item in folder_items)
        if not folder_lines:
            folder_lines = "No folders selected"
        last_sync = connection.last_sync_stats or {}
        sync_summary = (
            f"Last sync: {last_sync.get('mode', 'never')} | indexed "
            f"{last_sync.get('indexed', 0)} | updated {last_sync.get('updated', 0)} | "
            f"deleted {last_sync.get('deleted', 0)} | failed {last_sync.get('failed', 0)}"
        )
        return (
            f"Connected to Google Drive using `{connection.auth_mode}`.\n\n"
            f"Folders: {folder_lines}\n\n{sync_summary}"
        )

    def load_state(self, user_id: Optional[str]):
        connection = self._get_connection(user_id)
        folder_choices = []
        folder_value = []
        if connection:
            folder_choices = [
                (item.get("label", item["id"]), item["id"])
                for item in connection.selected_folders.get("items", [])
            ]
            folder_value = [item["id"] for item in connection.selected_folders.get("items", [])]

        return (
            self._status_text(user_id, connection),
            gr.update(choices=folder_choices, value=folder_value),
            "",
            "",
            "",
            "",
            "",
        )

    def connect_drive(self, user_id: Optional[str], auth_mode: str):
        if user_id is None:
            raise gr.Error("Please sign in before connecting Google Drive")

        if auth_mode == "service_account":
            if not self._config.has_service_account:
                raise gr.Error("Google Drive service account is not configured")
            if not self._is_admin(user_id):
                raise gr.Error("Only admins can use the configured service account")
            metadata = {}
            if self._config.service_account_subject:
                metadata["service_account_subject"] = self._config.service_account_subject
            connection = self._store.save_connection(
                user_id=str(user_id),
                index_id=self._index.id,
                auth_mode="service_account",
                metadata=metadata,
            )
            return (
                self._status_text(user_id, connection),
                "",
                "",
                "Service account connection saved.",
                "",
            )

        oauth = self._auth.begin_oauth(str(user_id), self._index.id)
        auth_link = (
            f"[Authorize Google Drive]({oauth.authorization_url})\n\n"
            f"After Google redirects, paste the full callback URL here. Redirect URI: "
            f"`{oauth.redirect_uri}`"
        )
        return (
            self._status_text(user_id, self._get_connection(user_id)),
            auth_link,
            oauth.state,
            "Open the authorization link, then paste the callback URL.",
            "",
        )

    def complete_oauth(
        self, user_id: Optional[str], oauth_state: str, callback_url: str
    ):
        if user_id is None:
            raise gr.Error("Please sign in before completing Google Drive OAuth")
        try:
            connection = self._auth.complete_oauth(
                str(user_id),
                self._index.id,
                oauth_state,
                callback_url,
            )
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
        return (
            self._status_text(user_id, connection),
            "",
            "",
            "",
            "Google Drive OAuth completed successfully.",
            "",
        )

    def disconnect_drive(self, user_id: Optional[str]):
        connection = self._get_connection(user_id)
        if connection:
            self._auth.disconnect(connection)
            self._store.delete_connection(str(user_id), self._index.id)
        return (
            self._status_text(user_id, None),
            "",
            "",
            "",
            gr.update(choices=[], value=[]),
            "Google Drive disconnected. Indexed files were kept intact.",
            "",
        )

    def _build_client(self, connection):
        try:
            credentials = self._auth.get_credentials(connection)
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
        return GoogleDriveClient(credentials)

    def refresh_folders(self, user_id: Optional[str]):
        connection = self._get_connection(user_id)
        if connection is None:
            raise gr.Error("Connect Google Drive before loading folders")
        client = self._build_client(connection)
        resolver = DriveFolderPathResolver(client)
        folders = client.list_folders(page_size=self._config.folder_page_size)
        resolver.prime(folders)
        choices = [(folder_choice_label(folder, resolver), folder.id) for folder in folders]
        selected = [item["id"] for item in connection.selected_folders.get("items", [])]
        return (
            self._status_text(user_id, connection),
            gr.update(choices=choices, value=selected),
            f"Loaded {len(choices)} Google Drive folders.",
            "",
        )

    def sync_drive(
        self,
        user_id: Optional[str],
        settings: dict,
        selected_folder_ids: list[str],
        manual_folder_ids: str,
        force_full_sync: bool,
    ):
        connection = self._get_connection(user_id)
        if connection is None:
            raise gr.Error("Connect Google Drive before syncing")

        folder_ids = extract_folder_ids(selected_folder_ids, manual_folder_ids)
        if not folder_ids:
            saved_items = connection.selected_folders.get("items", [])
            folder_ids = [item["id"] for item in saved_items]
        if not folder_ids:
            raise gr.Error("Select at least one Google Drive folder before syncing")
        previous_folder_ids = {
            item["id"] for item in connection.selected_folders.get("items", [])
        }
        if previous_folder_ids and previous_folder_ids != set(folder_ids):
            force_full_sync = True

        client = self._build_client(connection)
        resolver = DriveFolderPathResolver(client)
        selected_items = []
        for folder_id in folder_ids:
            try:
                folder = client.get_file(folder_id)
            except Exception:
                if folder_id == "root":
                    folder = client.list_folders(page_size=1)[0]
                else:
                    raise
            resolver.prime([folder])
            selected_items.append(
                {"id": folder_id, "label": folder_choice_label(folder, resolver)}
            )

        connection = self._store.update_connection(
            connection.id,
            selected_folders={"items": selected_items},
        )
        adapter = KotaemonIndexAdapter(self._index, settings, str(user_id))
        engine = DriveSyncEngine(
            client=client,
            exporter=DriveExporter(client),
            adapter=adapter,
            state_store=self._store,
            index_config=self._index.config,
        )

        logs: list[str] = []
        if previous_folder_ids and previous_folder_ids != set(folder_ids):
            logs.append("Folder selection changed; running a full sync.")
        result = engine.sync(
            connection,
            selected_folder_ids=folder_ids,
            force_full=force_full_sync,
            log=logs.append,
        )
        connection = self._get_connection(user_id)
        folder_choices = [
            (item["label"], item["id"])
            for item in connection.selected_folders.get("items", [])
        ]
        summary = json.dumps(result.to_dict(), indent=2)
        return (
            self._status_text(user_id, connection),
            gr.update(choices=folder_choices, value=folder_ids),
            summary,
            "\n".join(logs + result.errors),
        )
