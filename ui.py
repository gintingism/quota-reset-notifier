from __future__ import annotations

import ctypes
import tkinter as tk
import time
from ctypes import wintypes
from datetime import datetime
from tkinter import colorchooser, messagebox
from typing import Callable
from urllib.parse import urlparse

import customtkinter as ctk

from config_manager import AppConfig, ConfigManager
from notifications import WeeklyQuotaReminder
from quota_fetcher import AggregatedQuotaState, ProviderSnapshot, QuotaFetcher
from timer_engine import TimerEngine


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
COLORS = {
    "surface": "#202020",
    "surface_raised": "#2B2B2B",
    "surface_subtle": "#252525",
    "border": "#3A3A3A",
    "muted": "#B8B8B8",
    "text": "#F5F5F5",
    "green": "#4ADE80",
    "orange": "#F59E0B",
    "red": "#F87171",
    "blue": "#8B7CF6",
}


def quota_color(percent: float | None) -> str:
    if percent is None:
        return COLORS["muted"]
    if percent > 50:
        return COLORS["green"]
    if percent >= 20:
        return COLORS["orange"]
    return COLORS["red"]


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent: "QuotaWidget", config: AppConfig,
                 on_save: Callable[[], None], focus_provider: str | None = None) -> None:
        super().__init__(parent)
        self.config, self.on_save = config, on_save
        self.title("Quota Reset Notifier Settings")
        self.geometry("680x760")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._build(focus_provider)

    def _build(self, focus_provider: str | None) -> None:
        ctk.CTkLabel(
            self, text="Settings", text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 22, "bold")
        ).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(
            self, text="Manage providers, refresh behavior, and appearance",
            text_color=COLORS["muted"], font=ctk.CTkFont("Segoe UI", 10)
        ).pack(anchor="w", padx=20, pady=(0, 14))
        frame = ctk.CTkScrollableFrame(self, fg_color=COLORS["surface_raised"])
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._section_label(frame, "Providers")
        ctk.CTkLabel(frame, text="Re-auth provider", text_color=COLORS["muted"]).pack(
            anchor="w", padx=8, pady=(4, 3)
        )
        self.provider = ctk.CTkComboBox(frame, values=["Antigravity", "GitHub Copilot"])
        self.provider.set("GitHub Copilot" if focus_provider == "github_copilot" else "Antigravity")
        self.provider.pack(fill="x", padx=8)
        self.antigravity_enabled = ctk.BooleanVar(value=self.config.antigravity.enabled)
        ctk.CTkCheckBox(frame, text="Enable Antigravity",
                        variable=self.antigravity_enabled).pack(anchor="w", padx=8, pady=(12, 3))
        self.ag_endpoint = self._field(frame, "Antigravity endpoint URL",
                                       self.config.antigravity.endpoint_url, False,
                                       "https://host.example/api/quota")
        self.ag_token = self._field(frame, "Antigravity session token",
                                    self.config.antigravity.session_token, True,
                                    "Paste session token…")
        self.ag_cookies = self._field(frame, "Antigravity cookies: name=value; name2=value2",
                                      self.config.antigravity.cookies, True,
                                      "session_id=…; other_cookie=…")
        self.ag_interval = self._field(frame, "Antigravity refresh interval (60-3600 sec)",
                                       str(self.config.antigravity.refresh_interval_sec), False,
                                       "600")
        self.copilot_enabled = ctk.BooleanVar(value=self.config.github_copilot.enabled)
        ctk.CTkCheckBox(frame, text="Enable GitHub Copilot",
                        variable=self.copilot_enabled).pack(anchor="w", padx=8, pady=(12, 3))
        self.gh_token = self._field(frame, "GitHub token",
                                    self.config.github_copilot.github_token, True,
                                    "ghp_… or github_pat_…")
        self.gh_endpoint = self._field(frame, "GitHub Copilot endpoint",
                                       self.config.github_copilot.endpoint_url, False,
                                       "https://api.github.com/…")
        self.gh_editor = self._field(frame, "Editor-Version header",
                                     self.config.github_copilot.editor_version, False,
                                     "vscode/1.99.0")
        self.gh_interval = self._field(frame, "GitHub refresh interval (60-3600 sec)",
                                       str(self.config.github_copilot.refresh_interval_sec), False,
                                       "300")
        self._section_label(frame, "Weekly notifications")
        ctk.CTkLabel(
            frame,
            text="Sources are best-effort: Copilot uses an undocumented internal endpoint; "
                 "Antigravity uses the configured/local usage source.",
            text_color=COLORS["muted"],
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 6))
        notifications = self.config.notifications
        self.notifications_enabled = ctk.BooleanVar(value=notifications.enabled)
        ctk.CTkCheckBox(
            frame, text="Enable Telegram/Discord weekly reminders",
            variable=self.notifications_enabled,
        ).pack(anchor="w", padx=8, pady=(4, 3))
        self.weekly_reminders = ctk.BooleanVar(value=notifications.weekly_reminders)
        ctk.CTkCheckBox(
            frame, text="Enable weekly reset reminder processing",
            variable=self.weekly_reminders,
        ).pack(anchor="w", padx=8, pady=3)
        self.visible_hello = ctk.BooleanVar(value=notifications.visible_hello)
        ctk.CTkCheckBox(
            frame, text="Send visible post-reset hello notification",
            variable=self.visible_hello,
        ).pack(anchor="w", padx=8, pady=3)
        self.telegram_token = self._field(
            frame, "Telegram bot token", notifications.telegram_bot_token, True,
            "123456:bot-token",
        )
        self.telegram_chat_id = self._field(
            frame, "Telegram chat ID", notifications.telegram_chat_id, False,
            "chat id",
        )
        self.discord_webhook = self._field(
            frame, "Discord webhook URL", notifications.discord_webhook_url, True,
            "https://discord.com/api/webhooks/…",
        )
        self.copilot_hello_endpoint = self._field(
            frame, "Optional GitHub Copilot post-reset hello endpoint (HTTPS)",
            notifications.provider_hello_endpoints.get("github_copilot", ""),
            False, "https://your-service.example/hooks/copilot",
        )
        self.antigravity_hello_endpoint = self._field(
            frame, "Optional Antigravity post-reset hello endpoint (HTTPS)",
            notifications.provider_hello_endpoints.get("antigravity", ""),
            False, "https://your-service.example/hooks/antigravity",
        )
        self._section_label(frame, "Reset schedule")
        self.reset_time = self._field(frame, "Fallback weekly reset time (HH:MM)",
                                      f"{self.config.weekly_reset_hour:02d}:{self.config.weekly_reset_minute:02d}",
                                      False, "00:00")
        ctk.CTkLabel(frame, text="Fallback weekly reset day").pack(anchor="w", padx=8, pady=(10, 3))
        self.weekday = ctk.CTkComboBox(frame, values=WEEKDAYS)
        self.weekday.set(WEEKDAYS[self.config.weekly_reset_weekday])
        self.weekday.pack(fill="x", padx=8)
        self._section_label(frame, "Appearance")
        self.always_top = ctk.BooleanVar(value=self.config.always_on_top)
        ctk.CTkCheckBox(frame, text="Always on top",
                        variable=self.always_top).pack(anchor="w", padx=8, pady=10)
        ctk.CTkButton(frame, text="Choose accent color",
                      command=self.choose_color).pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(self, text="Save & Apply", height=38, command=self.save).pack(
            fill="x", padx=16, pady=(8, 16)
        )

    @staticmethod
    def _section_label(parent: ctk.CTkFrame, text: str) -> None:
        ctk.CTkLabel(parent, text=text.upper(), text_color=COLORS["muted"],
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(
                         anchor="w", padx=8, pady=(16, 4))

    @staticmethod
    def _field(parent, label: str, value: str, secret: bool = False,
               placeholder: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label).pack(anchor="w", padx=8, pady=(8, 3))
        field = ctk.CTkEntry(parent, show="*" if secret else "",
                             placeholder_text=placeholder)
        if value:
            field.insert(0, value)
        field.pack(fill="x", padx=8)
        return field

    def choose_color(self) -> None:
        result = colorchooser.askcolor(color=self.config.accent_color, parent=self)
        if result[1]:
            self.config.accent_color = result[1]

    def save(self) -> None:
        try:
            hour, minute = map(int, self.reset_time.get().strip().split(":"))
            ag_interval, gh_interval = int(self.ag_interval.get()), int(self.gh_interval.get())
            provider_endpoints = (
                self.copilot_hello_endpoint.get().strip(),
                self.antigravity_hello_endpoint.get().strip(),
            )
            if not (0 <= hour <= 23 and 0 <= minute <= 59
                    and 60 <= ag_interval <= 3600 and 60 <= gh_interval <= 3600
                    and all(
                        not endpoint
                        or (urlparse(endpoint).scheme == "https" and bool(urlparse(endpoint).netloc))
                        for endpoint in provider_endpoints
                    )):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid input",
                                 "Gunakan HH:MM dan interval 60-3600 detik.",
                                 parent=self)
            return
        ag = self.config.antigravity
        ag.enabled, ag.endpoint_url = self.antigravity_enabled.get(), self.ag_endpoint.get().strip()
        ag.session_token, ag.cookies = self.ag_token.get().strip(), self.ag_cookies.get().strip()
        ag.refresh_interval_sec = ag_interval
        gh = self.config.github_copilot
        gh.enabled, gh.github_token = self.copilot_enabled.get(), self.gh_token.get().strip()
        gh.endpoint_url, gh.editor_version = self.gh_endpoint.get().strip(), self.gh_editor.get().strip()
        gh.refresh_interval_sec = gh_interval
        notifications = self.config.notifications
        notifications.enabled = self.notifications_enabled.get()
        notifications.weekly_reminders = self.weekly_reminders.get()
        notifications.visible_hello = self.visible_hello.get()
        notifications.telegram_bot_token = self.telegram_token.get().strip()
        notifications.telegram_chat_id = self.telegram_chat_id.get().strip()
        notifications.discord_webhook_url = self.discord_webhook.get().strip()
        notifications.provider_hello_endpoints = {
            provider: endpoint
            for provider, endpoint in {
                "github_copilot": self.copilot_hello_endpoint.get().strip(),
                "antigravity": self.antigravity_hello_endpoint.get().strip(),
            }.items()
            if endpoint
        }
        self.config.weekly_reset_weekday = WEEKDAYS.index(self.weekday.get())
        self.config.weekly_reset_hour, self.config.weekly_reset_minute = hour, minute
        self.config.always_on_top = self.always_top.get()
        self.on_save()
        self.destroy()


class QuotaWidget(ctk.CTk):
    def __init__(self, config: AppConfig, manager: ConfigManager,
                 on_exit: Callable[[], None]) -> None:
        super().__init__()
        self.config, self.manager, self.on_exit = config, manager, on_exit
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("Quota Reset Notifier")
        self.overrideredirect(True)
        self.attributes("-alpha", max(0.95, config.window_alpha))
        self.attributes("-topmost", config.always_on_top)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.engine = TimerEngine(config.rolling_reset_at, config.weekly_reset_override,
                                  config.weekly_reset_weekday, config.weekly_reset_hour,
                                  config.weekly_reset_minute)
        self.expanded = False
        self.last_state = AggregatedQuotaState()
        self.reminder = WeeklyQuotaReminder.from_config(config.notifications)
        self._fetcher_generation = 0
        self.fetcher = self._new_fetcher()
        self._drag_start: tuple[int, int] | None = None
        self._resize_job: str | None = None
        self._build()
        self.set_mode()
        self.bind("<ButtonPress-1>", self._drag_begin)
        self.bind("<B1-Motion>", self._drag_move)
        self.bind("<Button-3>", lambda _event: self.open_settings())
        self.after(250, self._tick)
        self.fetcher.start()

    def _new_fetcher(self) -> QuotaFetcher:
        generation = self._fetcher_generation
        return QuotaFetcher(self.config, lambda state: self._enqueue_state(generation, state))

    def _enqueue_state(self, generation: int, state: AggregatedQuotaState) -> None:
        if generation != self._fetcher_generation:
            return
        try:
            self.after(0, self._apply_if_current, generation, state)
        except tk.TclError:
            pass

    def _apply_if_current(self, generation: int, state: AggregatedQuotaState) -> None:
        if generation == self._fetcher_generation:
            self.apply_state(state)

    def _build(self) -> None:
        self.card = ctk.CTkFrame(self, corner_radius=18, fg_color=COLORS["surface"],
                                 border_width=1, border_color=COLORS["border"])
        self.card.pack(fill="both", expand=True, padx=2, pady=2)
        self.header = ctk.CTkFrame(self.card, fg_color="transparent")
        self.header.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(self.header, text="AI quota", text_color=COLORS["text"],
                     font=ctk.CTkFont("Segoe UI", 15, "bold")).pack(side="left")
        self.status_dot = ctk.CTkLabel(self.header, text="●", text_color=COLORS["muted"],
                                       font=ctk.CTkFont("Segoe UI", 13))
        self.status_dot.pack(side="left", padx=(8, 3))
        self.status = ctk.CTkLabel(self.header, text="SYNCING…", text_color=COLORS["muted"],
                                   font=ctk.CTkFont("Segoe UI", 10))
        self.status.pack(side="left")
        self.refresh_button = ctk.CTkButton(self.header, text="Refresh", width=66, height=26,
                                            fg_color="transparent", hover_color=COLORS["border"],
                                            text_color=COLORS["text"], font=ctk.CTkFont("Segoe UI", 10),
                                            command=self.refresh_now)
        self.refresh_button.pack(side="right", padx=(6, 0))
        self.settings_button = ctk.CTkButton(self.header, text="Settings", width=72, height=26,
                                             fg_color="transparent", hover_color=COLORS["border"],
                                             text_color=COLORS["text"], font=ctk.CTkFont("Segoe UI", 10),
                                             command=self.open_settings)
        self.settings_button.pack(side="right", padx=(6, 0))
        self.close_button = ctk.CTkButton(self.header, text="×", width=28, height=24,
                                          fg_color="transparent", hover_color=COLORS["border"],
                                          text_color=COLORS["muted"], command=self.hide_to_tray)
        self.close_button.pack(side="right")
        ctk.CTkLabel(self.card, text="Quota at a glance", text_color=COLORS["muted"],
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(10, 0))
        primary = ctk.CTkFrame(self.card, fg_color="transparent")
        primary.pack(fill="x", padx=18, pady=(0, 2))
        self.primary_value = ctk.CTkLabel(
            primary, text="--%", text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 30, "bold"),
        )
        self.primary_value.pack(side="left")
        self.primary_label = ctk.CTkLabel(
            primary, text="Premium interactions remaining", text_color=COLORS["text"],
            anchor="w", justify="left", wraplength=180,
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
        )
        self.primary_label.pack(side="left", padx=(10, 0))
        self.summary_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.summary_frame.pack(fill="x", padx=16, pady=(2, 0))
        self.ag_summary = self._summary_row(self.summary_frame, "Antigravity")
        self.gh_summary = self._summary_row(self.summary_frame, "Copilot")
        self.reset = ctk.CTkLabel(self.card, text="Nearest reset  •  --",
                                  text_color=COLORS["muted"], font=ctk.CTkFont("Segoe UI", 10))
        self.reset.pack(pady=(6, 12))
        self.details_button = ctk.CTkButton(self.card, text="Show details", height=28,
                                            fg_color=COLORS["surface_subtle"],
                                            hover_color=COLORS["border"],
                                            text_color=COLORS["text"],
                                            command=self.toggle_expand)
        self.details_button.pack(fill="x", padx=18, pady=(0, 12))
        self.details = ctk.CTkFrame(self.card, fg_color="transparent")
        self.ag_card = self._provider_card(self.details, "GOOGLE ANTIGRAVITY")
        self.gh_card = self._provider_card(self.details, "GITHUB COPILOT")
        self.action = ctk.CTkButton(self.card, text="Triggered session", height=28,
                                    fg_color=self.config.accent_color, hover_color="#6D5DD3",
                                    command=self.trigger_session)

    def _summary_row(self, parent: ctk.CTkFrame, name: str) -> dict[str, ctk.CTkBaseClass]:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(side="left", fill="x", expand=True, padx=(0, 5 if name == "Antigravity" else 0))
        label = ctk.CTkLabel(row, text=name, text_color=COLORS["muted"],
                             font=ctk.CTkFont("Segoe UI", 10))
        label.pack(anchor="w")
        bar = ctk.CTkProgressBar(row, height=8, corner_radius=4, fg_color=COLORS["border"],
                                 progress_color=COLORS["muted"])
        bar.set(0)
        bar.pack(side="left", fill="x", expand=True, pady=(3, 0))
        value = ctk.CTkLabel(row, text="--%", width=42, text_color=COLORS["text"],
                             font=ctk.CTkFont("Segoe UI", 11, "bold"))
        value.pack(side="right", padx=(6, 0))
        return {"row": row, "bar": bar, "value": value}

    def _provider_card(self, parent: ctk.CTkFrame, title: str) -> dict[str, Any]:
        card = ctk.CTkFrame(parent, fg_color=COLORS["surface_raised"], corner_radius=8,
                            border_width=1, border_color=COLORS["border"])
        card.pack(side="left", fill="both", expand=True, padx=(0, 6 if "ANTIGRAVITY" in title else 0))
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 0))
        heading = ctk.CTkLabel(header, text=title.title(), text_color=self.config.accent_color,
                               font=ctk.CTkFont("Segoe UI", 10, "bold"))
        heading.pack(side="left")
        badge = ctk.CTkLabel(header, text="--", text_color=COLORS["muted"],
                             fg_color=COLORS["border"], corner_radius=8,
                             font=ctk.CTkFont("Segoe UI", 9, "bold"))
        badge.pack(side="right", padx=(4, 0))
        metric = ctk.CTkLabel(card, text="--%", text_color=COLORS["muted"],
                              font=ctk.CTkFont("Segoe UI", 28, "bold"))
        metric.pack(anchor="w", padx=12, pady=(5, 0))
        metric_label = ctk.CTkLabel(card, text="Remaining", text_color=COLORS["muted"],
                                    font=ctk.CTkFont("Segoe UI", 10))
        metric_label.pack(anchor="w", padx=12)
        counts = ctk.CTkLabel(card, text="Counts unavailable", text_color=COLORS["text"],
                              anchor="w", font=ctk.CTkFont("Segoe UI", 10))
        counts.pack(fill="x", padx=12, pady=(5, 0))
        rows = ctk.CTkLabel(card, text="Waiting for sync…", justify="left", anchor="w",
                            text_color=COLORS["text"], wraplength=175,
                            font=ctk.CTkFont("Segoe UI", 10))
        rows.pack(fill="x", padx=12, pady=(5, 0))
        reset = ctk.CTkLabel(card, text="Reset --", text_color=COLORS["muted"],
                             anchor="w", font=ctk.CTkFont("Segoe UI", 9))
        reset.pack(fill="x", padx=12, pady=(5, 10))
        return {
            "card": card, "heading": heading, "badge": badge, "metric": metric,
            "metric_label": metric_label, "counts": counts, "rows": rows, "reset": reset,
        }

    @staticmethod
    def _format(seconds: int) -> str:
        days, remainder = divmod(max(0, seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}" if days else f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _date(epoch: float | None) -> str:
        return datetime.fromtimestamp(epoch).strftime("%d %b %H:%M") if epoch else "--"

    @staticmethod
    def _model_percent(snapshot: ProviderSnapshot, *names: str) -> float | None:
        for model in snapshot.models:
            if any(name in model.name.lower() for name in names):
                return model.remaining_percent
        return None

    @staticmethod
    def _display_percent(value: float | None) -> str:
        return f"{value:.0f}%" if value is not None else "--%"

    @staticmethod
    def _model_details(snapshot: ProviderSnapshot) -> str:
        details = []
        for model in snapshot.models:
            status = QuotaWidget._display_percent(model.remaining_percent)
            if model.unlimited:
                status += " unlimited"
            elif model.remaining is not None and model.entitlement is not None:
                status += f" ({model.remaining:g}/{model.entitlement:g})"
            details.append(f"{model.name} {status}")
        return "\n".join(details)

    @staticmethod
    def _count_text(model: Any) -> str:
        if model is None:
            return "Counts unavailable"
        if model.unlimited:
            return "Unlimited"
        if model.remaining is not None and model.entitlement is not None:
            used = model.used
            if used is None:
                used = max(0.0, model.entitlement - model.remaining)
            return f"{used:g} used  •  {model.remaining:g} remaining"
        return "Counts unavailable"

    def _set_provider_card(
        self, card: dict[str, Any], snapshot: ProviderSnapshot, percent: float | None,
        label: str, model: Any = None,
    ) -> None:
        color = quota_color(percent)
        unavailable = bool(snapshot.error) or percent is None
        card["metric"].configure(text=self._display_percent(percent), text_color=color)
        card["metric_label"].configure(text=label)
        card["badge"].configure(
            text=snapshot.plan_tier if snapshot.plan_tier != "Unknown" else (
                "Offline" if snapshot.error else "Connected"
            ),
            text_color=color if not snapshot.error else COLORS["red"],
        )
        card["counts"].configure(text=self._count_text(model))
        if unavailable:
            card["rows"].configure(
                text=snapshot.error or snapshot.account_status or "Quota unavailable",
                text_color=COLORS["orange"] if not snapshot.error else COLORS["red"],
            )
        else:
            card["rows"].configure(text=self._model_details(snapshot) or "No category breakdown")
        reset_at = snapshot.reset_at or snapshot.rolling_reset_at or snapshot.weekly_reset_at
        card["reset"].configure(text=f"Reset  {self._date(reset_at)}")

    def _set_summary(self, summary: dict[str, ctk.CTkBaseClass], percent: float | None) -> None:
        color = quota_color(percent)
        summary["bar"].configure(progress_color=color)
        summary["bar"].set((percent or 0) / 100)
        summary["value"].configure(text=f"{percent:.0f}%" if percent is not None else "--%",
                                    text_color=color)

    def _tick(self) -> None:
        ag = self.last_state.providers.get("antigravity")
        local = self.engine.snapshot()
        rolling = ag.rolling_reset_at if ag and ag.rolling_reset_at else self.engine.rolling_reset_at
        weekly = ag.weekly_reset_at if ag and ag.weekly_reset_at else local.weekly_reset_at.timestamp()
        now = time.time()
        values = [value for value in (rolling, weekly) if value and value > now]
        nearest = min(values) if values else None
        self.reset.configure(text=f"Nearest reset  •  {self._format(int(nearest - now))}"
                             if nearest else "Nearest reset  •  --")
        self.after(250, self._tick)

    def apply_state(self, state: AggregatedQuotaState) -> None:
        self.last_state = state
        try:
            self.reminder.process(state)
        except Exception:
            # Notification delivery must not interrupt UI state updates.
            pass
        ag = state.providers.get("antigravity", ProviderSnapshot("antigravity"))
        gh = state.providers.get("github_copilot", ProviderSnapshot("github_copilot"))
        if ag.rolling_reset_at:
            self.engine.rolling_reset_at = ag.rolling_reset_at
            self.config.rolling_reset_at = ag.rolling_reset_at
        if ag.weekly_reset_at:
            self.engine.weekly_override = ag.weekly_reset_at
            self.config.weekly_reset_override = ag.weekly_reset_at
        enabled = [
            snapshot for snapshot, configured in (
                (ag, self.config.antigravity.enabled),
                (gh, self.config.github_copilot.enabled),
            ) if configured
        ]
        errors = [snapshot.error for snapshot in enabled if snapshot.error]
        synced = [snapshot for snapshot in enabled if snapshot.source == "remote" and not snapshot.error]
        offline = bool(enabled) and not synced
        quota_unavailable = any(
            snapshot.provider == "github_copilot"
            and snapshot.source == "remote"
            and not snapshot.error
            and snapshot.quota_percent is None
            for snapshot in enabled
        )
        status_color = (
            COLORS["red"] if offline
            else COLORS["orange"] if errors or quota_unavailable
            else COLORS["green"]
        )
        self.status_dot.configure(text_color=status_color)
        self.status.configure(
            text="OFFLINE" if offline else "LIMITED" if quota_unavailable else "PARTIAL" if errors else "SYNCED",
            text_color=status_color,
        )
        ag_percent = self._model_percent(ag, "gemini pro", "pro")
        self._set_summary(self.ag_summary, ag_percent)
        self._set_summary(self.gh_summary, gh.quota_percent)
        self.primary_value.configure(
            text=self._display_percent(gh.quota_percent),
            text_color=quota_color(gh.quota_percent),
        )
        self.primary_label.configure(
            text="Premium interactions remaining"
            if gh.quota_percent is not None
            else "Premium interactions\nquota unavailable",
        )
        ag_model = next((model for model in ag.models
                         if "gemini pro" in model.name.lower() or model.name.lower() == "pro"), None)
        gh_model = next((model for model in gh.models
                         if model.name.lower() == "premium_interactions"), None)
        self._set_provider_card(self.ag_card, ag, ag_percent, "Gemini Pro remaining", ag_model)
        self._set_provider_card(
            self.gh_card, gh, gh.quota_percent, "Premium interactions remaining", gh_model
        )

    def toggle_expand(self) -> None:
        self.expanded = not self.expanded
        self.details_button.configure(text="Hide details" if self.expanded else "Show details")
        if self.expanded:
            self.details.pack(fill="both", expand=True, padx=16, pady=(0, 8))
            self.action.pack(fill="x", padx=32, pady=(3, 12))
        else:
            self.details.pack_forget()
            self.action.pack_forget()
        self._animate_resize()

    def _animate_resize(self) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_step(0)

    def _resize_step(self, step: int) -> None:
        target_width, target_height = (440, 430) if self.expanded else (440, 220)
        start_width, start_height = (440, 220) if self.expanded else (440, 430)
        progress = min(1.0, (step + 1) / 5)
        width = round(start_width + (target_width - start_width) * progress)
        height = round(start_height + (target_height - start_height) * progress)
        self._set_geometry(width, height)
        if progress < 1:
            self._resize_job = self.after(24, self._resize_step, step + 1)

    def set_mode(self) -> None:
        self._set_geometry(440, 430 if self.expanded else 220)

    def _set_geometry(self, width: int, height: int) -> None:
        if self.config.ui_mode == "docked":
            _, _, right, bottom = self._work_area()
            self.geometry(f"{width}x{height}+{right - width - 10}+{bottom - height - 6}")
        elif self.config.window_x is not None and self.config.window_y is not None:
            self.geometry(f"{width}x{height}+{self.config.window_x}+{self.config.window_y}")
        else:
            self.geometry(f"{width}x{height}")

    @staticmethod
    def _work_area() -> tuple[int, int, int, int]:
        try:
            user32 = ctypes.windll.user32
            monitor = user32.MonitorFromPoint(wintypes.POINT(0, 0), 2)
            info = wintypes.MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            user32.GetMonitorInfoW(monitor, ctypes.byref(info))
            rect = info.rcWork
            return rect.left, rect.top, rect.right, rect.bottom
        except (AttributeError, OSError):
            return 0, 0, 1920, 1040

    def toggle_mode(self) -> None:
        self.config.ui_mode = "floating" if self.config.ui_mode == "docked" else "docked"
        self.manager.save(self.config)
        self.set_mode()

    def trigger_session(self) -> None:
        self.engine.trigger_session()
        self.config.rolling_reset_at = self.engine.rolling_reset_at
        self.manager.save(self.config)

    def refresh_now(self) -> None:
        self.status_dot.configure(text_color=COLORS["orange"])
        self.status.configure(text="SYNCING…", text_color=COLORS["orange"])
        self.fetcher.refresh_now()

    def _drag_begin(self, event) -> None:
        self._drag_start = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_move(self, event) -> None:
        if self._drag_start and self.config.ui_mode == "floating":
            self.geometry(f"+{event.x_root - self._drag_start[0]}+{event.y_root - self._drag_start[1]}")

    def save_position(self) -> None:
        self.config.window_x, self.config.window_y = self.winfo_x(), self.winfo_y()
        self.manager.save(self.config)

    def show(self) -> None:
        self.deiconify()
        self.lift()

    def hide_to_tray(self) -> None:
        self.save_position()
        self.withdraw()

    def open_settings(self, focus_provider: str | None = None) -> None:
        SettingsWindow(self, self.config, self._settings_saved, focus_provider)

    def _settings_saved(self) -> None:
        self.fetcher.stop()
        self._fetcher_generation += 1
        self.reminder = WeeklyQuotaReminder.from_config(self.config.notifications)
        self.fetcher = self._new_fetcher()
        self.fetcher.start()
        self.attributes("-topmost", self.config.always_on_top)
        self.manager.save(self.config)
        self.show()
