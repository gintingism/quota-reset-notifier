from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from github_auth import detect_github_token


APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "AIQuotaWidget"
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class AntigravityConfig:
    enabled: bool = False
    local_reader: bool = True
    endpoint_url: str = ""
    session_token: str = ""
    cookies: str = ""
    refresh_interval_sec: int = 600


@dataclass
class GitHubCopilotConfig:
    enabled: bool = False
    github_token: str = ""
    refresh_interval_sec: int = 300
    endpoint_url: str = "https://api.github.com/copilot_internal/user"
    editor_version: str = "vscode/1.99.0"


@dataclass
class SyncRelayConfig:
    enabled: bool = False
    base_url: str = ""
    auth_token: str = ""
    interval_sec: int = 300


@dataclass
class NotificationConfig:
    enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    weekly_reminders: bool = True
    visible_hello: bool = True
    provider_hello_endpoints: dict[str, str] = field(default_factory=dict)
    provider_hello_timeout_sec: float = 10.0
    stale_after_sec: int = 900
    retry_attempts: int = 3
    retry_backoff_sec: float = 1.0


@dataclass
class AppConfig:
    theme: str = "dark"
    accent_color: str = "#7C3AED"
    text_color: str = "#F9FAFB"
    background_color: str = "#111827"
    window_alpha: float = 0.94
    always_on_top: bool = True
    window_x: int | None = None
    window_y: int | None = None
    weekly_reset_weekday: int = 0
    weekly_reset_hour: int = 0
    weekly_reset_minute: int = 0
    weekly_reset_timezone: str = "local"
    rolling_reset_at: float | None = None
    weekly_reset_override: float | None = None
    ui_mode: str = "docked"
    antigravity: AntigravityConfig = field(default_factory=AntigravityConfig)
    github_copilot: GitHubCopilotConfig = field(default_factory=GitHubCopilotConfig)
    sync_relay: SyncRelayConfig = field(default_factory=SyncRelayConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


class ConfigManager:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> AppConfig:
        values: dict[str, Any] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    values = loaded
            except (OSError, json.JSONDecodeError):
                pass
        config = AppConfig()
        self._apply_values(config, values)
        self._migrate_legacy(config, values)
        self._normalize(config)
        return config

    def save(self, config: AppConfig) -> None:
        self._normalize(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(config), indent=2, ensure_ascii=True)
        fd, temporary = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def auto_configure_github_token(self, force: bool = False) -> str | None:
        """Detect a local GitHub token and persist it without ever printing it."""
        config = self.load()
        if config.github_copilot.github_token and not force:
            return config.github_copilot.github_token
        token, _source = detect_github_token()
        if not token:
            return None
        config.github_copilot.github_token = token
        config.github_copilot.enabled = True
        self.save(config)
        return token

    @staticmethod
    def _apply_values(config: AppConfig, values: dict[str, Any]) -> None:
        scalar_fields = {
            "theme", "accent_color", "text_color", "background_color", "window_alpha",
            "always_on_top", "window_x", "window_y", "weekly_reset_weekday",
            "weekly_reset_hour", "weekly_reset_minute", "weekly_reset_timezone",
            "rolling_reset_at", "weekly_reset_override", "ui_mode",
        }
        for key in scalar_fields:
            if key in values:
                setattr(config, key, values[key])
        for key, target in (
            ("antigravity", config.antigravity),
            ("github_copilot", config.github_copilot),
            ("sync_relay", config.sync_relay),
            ("notifications", config.notifications),
        ):
            nested = values.get(key)
            if isinstance(nested, dict):
                for field_name in asdict(target):
                    if field_name in nested:
                        setattr(target, field_name, nested[field_name])

    @staticmethod
    def _migrate_legacy(config: AppConfig, values: dict[str, Any]) -> None:
        if not isinstance(values.get("antigravity"), dict):
            config.antigravity.enabled = bool(
                values.get("quota_endpoint") or values.get("session_token") or values.get("bearer_token")
            )
            config.antigravity.endpoint_url = str(values.get("quota_endpoint", "") or "")
            config.antigravity.session_token = str(
                values.get("bearer_token") or values.get("session_token") or ""
            )
            config.antigravity.cookies = str(values.get("cookies", "") or "")
            config.antigravity.refresh_interval_sec = int(values.get("poll_interval_seconds", 600) or 600)

    @staticmethod
    def _normalize(config: AppConfig) -> None:
        config.theme = config.theme if config.theme in {"dark", "light", "system"} else "dark"
        config.window_alpha = min(1.0, max(0.55, ConfigManager._number(config.window_alpha, 0.94)))
        config.weekly_reset_weekday = min(6, max(0, ConfigManager._integer(config.weekly_reset_weekday, 0)))
        config.weekly_reset_hour = min(23, max(0, ConfigManager._integer(config.weekly_reset_hour, 0)))
        config.weekly_reset_minute = min(59, max(0, ConfigManager._integer(config.weekly_reset_minute, 0)))
        config.always_on_top = bool(config.always_on_top)
        config.ui_mode = config.ui_mode if config.ui_mode in {"docked", "floating"} else "docked"
        config.antigravity.enabled = bool(config.antigravity.enabled)
        config.antigravity.refresh_interval_sec = min(
            3600, max(60, ConfigManager._integer(config.antigravity.refresh_interval_sec, 600))
        )
        config.github_copilot.enabled = bool(config.github_copilot.enabled)
        config.github_copilot.refresh_interval_sec = min(
            3600, max(60, ConfigManager._integer(config.github_copilot.refresh_interval_sec, 300))
        )
        config.sync_relay.enabled = bool(config.sync_relay.enabled)
        config.sync_relay.interval_sec = min(
            3600, max(60, ConfigManager._integer(config.sync_relay.interval_sec, 300))
        )
        config.notifications.enabled = bool(config.notifications.enabled)
        config.notifications.weekly_reminders = bool(config.notifications.weekly_reminders)
        config.notifications.stale_after_sec = min(
            86400, max(60, ConfigManager._integer(config.notifications.stale_after_sec, 900))
        )
        config.notifications.retry_attempts = min(
            8, max(1, ConfigManager._integer(config.notifications.retry_attempts, 3))
        )
        config.notifications.retry_backoff_sec = min(
            60.0, max(0.0, ConfigManager._number(config.notifications.retry_backoff_sec, 1.0))
        )
        config.notifications.visible_hello = bool(config.notifications.visible_hello)
        if not isinstance(config.notifications.provider_hello_endpoints, dict):
            config.notifications.provider_hello_endpoints = {}
        config.notifications.provider_hello_endpoints = {
            str(provider).strip(): str(endpoint).strip()
            for provider, endpoint in config.notifications.provider_hello_endpoints.items()
            if str(provider).strip() and isinstance(endpoint, str) and endpoint.strip()
        }
        config.notifications.provider_hello_timeout_sec = min(
            30.0, max(1.0, ConfigManager._number(
                config.notifications.provider_hello_timeout_sec, 10.0
            ))
        )

    @staticmethod
    def _integer(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _number(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
