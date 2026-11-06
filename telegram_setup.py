from __future__ import annotations

import getpass
import time
from typing import Any, Callable

import requests

from config_manager import ConfigManager


class TelegramSetupError(RuntimeError):
    pass


def telegram_api(
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    request: Callable[..., Any] = requests.post,
) -> dict[str, Any]:
    if not token.strip():
        raise TelegramSetupError("Telegram bot token is required")
    response = request(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload or {},
        timeout=15,
    )
    try:
        body = response.json()
    except (ValueError, TypeError) as error:
        raise TelegramSetupError("Telegram returned an invalid response") from error
    if response.status_code < 200 or response.status_code >= 300 or not body.get("ok"):
        raise TelegramSetupError(str(body.get("description", "Telegram request failed")))
    return body


def find_chat_id(
    token: str,
    wait_sec: int = 120,
    poll_sec: int = 3,
    request: Callable[..., Any] = requests.post,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
) -> tuple[str, str]:
    deadline = now() + max(1, wait_sec)
    offset: int | None = None
    while now() <= deadline:
        payload = {"timeout": min(10, max(1, int(deadline - now())))}
        if offset is not None:
            payload["offset"] = offset
        body = telegram_api(token, "getUpdates", payload, request)
        updates = body.get("result", [])
        if not isinstance(updates, list):
            raise TelegramSetupError("Telegram returned an invalid updates list")
        for update in updates:
            if not isinstance(update, dict):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
            chat = _chat_from_update(update)
            if chat:
                return chat
        sleep(min(max(0, poll_sec), max(0, deadline - now())))
    raise TelegramSetupError("No Telegram message received before the timeout")


def configure_telegram(
    manager: ConfigManager,
    token: str,
    chat_id: str,
    send_test: bool = True,
    request: Callable[..., Any] = requests.post,
) -> None:
    config = manager.load()
    config.notifications.telegram_bot_token = token.strip()
    config.notifications.telegram_chat_id = chat_id.strip()
    config.notifications.enabled = True
    config.notifications.weekly_reminders = True
    config.notifications.visible_hello = True
    manager.save(config)
    if send_test:
        telegram_api(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": "Quota Reset Notifier connected."},
            request,
        )


def _chat_from_update(update: dict[str, Any]) -> tuple[str, str] | None:
    message = update.get("message") or update.get("channel_post")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None
    chat_id = str(chat["id"])
    label = str(chat.get("title") or chat.get("username") or chat.get("first_name") or chat_id)
    return chat_id, label


def main() -> int:
    print("Telegram setup")
    print("1. Open your bot in Telegram.")
    print("2. Press Start and send a message such as: hello")
    token = getpass.getpass("Bot token (hidden): ").strip()
    try:
        telegram_api(token, "getMe")
        print("Waiting for a message from the bot destination...")
        chat_id, label = find_chat_id(token)
        configure_telegram(ConfigManager(), token, chat_id)
    except (TelegramSetupError, requests.RequestException) as error:
        print(f"Setup failed: {error}")
        return 1
    print(f"Telegram configured for {label}.")
    print("The token was saved only to the local application config.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
