from __future__ import annotations

import time
from typing import Any, Callable, Protocol

import requests
from urllib.parse import urlparse

from config_manager import NotificationConfig
from quota_models import AggregatedQuotaState, ProviderSnapshot


class RetryableNotificationError(RuntimeError):
    pass


class PermanentNotificationError(RuntimeError):
    pass


class Notifier(Protocol):
    def send(self, message: str) -> bool:
        ...


class TelegramNotifier:
    def __init__(
        self,
        token: str,
        chat_id: str,
        request: Callable[..., Any] = requests.post,
    ) -> None:
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.request = request

    def send(self, message: str) -> bool:
        response = self.request(
            self.url,
            json={"chat_id": self.chat_id, "text": message},
            timeout=10,
        )
        _check_response(response)
        return True


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: str,
        request: Callable[..., Any] = requests.post,
    ) -> None:
        self.webhook_url = webhook_url
        self.request = request

    def send(self, message: str) -> bool:
        response = self.request(
            self.webhook_url,
            json={"content": message},
            timeout=10,
        )
        _check_response(response)
        return True


class ProviderHelloNotifier:
    """Opt-in provider callback; it sends no credentials and only a fixed event."""

    def __init__(
        self,
        endpoint: str,
        provider: str,
        timeout_sec: float = 10.0,
        request: Callable[..., Any] = requests.post,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("provider hello endpoint must use HTTPS")
        self.endpoint = endpoint
        self.provider = provider
        self.timeout_sec = timeout_sec
        self.request = request

    def send(self, message: str) -> bool:
        response = self.request(
            self.endpoint,
            json={"event": "post-reset hello", "provider": self.provider, "message": message},
            timeout=self.timeout_sec,
        )
        _check_response(response)
        return True


def _check_response(response: Any) -> None:
    status = int(response.status_code)
    if 200 <= status < 300:
        return
    if status == 429 or status >= 500:
        raise RetryableNotificationError(f"notification provider returned {status}")
    raise PermanentNotificationError(f"notification provider returned {status}")


class NotificationDispatcher:
    def __init__(
        self,
        notifiers: list[Notifier],
        attempts: int = 3,
        backoff_sec: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.notifiers = notifiers
        self.attempts = max(1, attempts)
        self.backoff_sec = max(0.0, backoff_sec)
        self.sleep = sleep

    def send(self, message: str) -> bool:
        delivered = False
        for notifier in self.notifiers:
            for attempt in range(self.attempts):
                try:
                    delivered = bool(notifier.send(message)) or delivered
                    if delivered:
                        break
                except (RetryableNotificationError, requests.RequestException, TimeoutError):
                    if attempt + 1 == self.attempts:
                        break
                    self.sleep(self.backoff_sec * (2 ** attempt))
                except (PermanentNotificationError, ValueError, TypeError):
                    break
        return delivered


class WeeklyQuotaReminder:
    def __init__(
        self,
        dispatcher: NotificationDispatcher,
        stale_after_sec: int = 900,
        provider_actions: dict[str, NotificationDispatcher] | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.stale_after_sec = stale_after_sec
        self.provider_actions = provider_actions or {}
        self._notified: set[tuple[str, float]] = set()

    @classmethod
    def from_config(cls, config: NotificationConfig) -> "WeeklyQuotaReminder":
        notifiers: list[Notifier] = []
        if config.enabled and config.weekly_reminders and config.visible_hello:
            if config.telegram_bot_token and config.telegram_chat_id:
                notifiers.append(TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id))
            if config.discord_webhook_url:
                notifiers.append(DiscordNotifier(config.discord_webhook_url))
        actions: dict[str, NotificationDispatcher] = {}
        if config.enabled and config.weekly_reminders:
            for provider, endpoint in config.provider_hello_endpoints.items():
                try:
                    actions[provider] = NotificationDispatcher(
                        [ProviderHelloNotifier(
                            endpoint, provider, config.provider_hello_timeout_sec
                        )],
                        config.retry_attempts,
                        config.retry_backoff_sec,
                    )
                except ValueError:
                    continue
        return cls(
            NotificationDispatcher(notifiers, config.retry_attempts, config.retry_backoff_sec),
            config.stale_after_sec,
            actions,
        )

    def process(self, state: AggregatedQuotaState, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        sent = False
        for provider, snapshot in state.providers.items():
            if not self._eligible(snapshot, current) or snapshot.weekly_reset_at is None:
                continue
            event = (provider, snapshot.weekly_reset_at)
            if snapshot.weekly_reset_at <= current and event not in self._notified:
                self._notified.add(event)
                message = f"{provider} post-reset hello: weekly quota reset is available."
                sent = self.dispatcher.send(message) or sent
                action = self.provider_actions.get(provider)
                if action:
                    try:
                        sent = action.send(message) or sent
                    except (PermanentNotificationError, RetryableNotificationError, requests.RequestException):
                        pass
        return sent

    def _eligible(self, snapshot: ProviderSnapshot, now: float) -> bool:
        return (
            snapshot.source == "remote"
            and not snapshot.estimated
            and not snapshot.error
            and snapshot.fetched_at > 0
            and now - snapshot.fetched_at <= self.stale_after_sec
        )
