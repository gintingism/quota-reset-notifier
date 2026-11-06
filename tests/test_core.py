from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parents[1]))

from config_manager import AppConfig, ConfigManager  # noqa: E402
from notifications import (  # noqa: E402
    DiscordNotifier,
    NotificationDispatcher,
    RetryableNotificationError,
    ProviderHelloNotifier,
    WeeklyQuotaReminder,
    TelegramNotifier,
)
from quota_fetcher import COPILOT_USER_ENDPOINT, QuotaFetcher  # noqa: E402
from provider_adapters import AntigravityUsageReader  # noqa: E402
from quota_models import AggregatedQuotaState  # noqa: E402
from sync_relay import state_payload  # noqa: E402
from telegram_setup import (  # noqa: E402
    TelegramSetupError,
    configure_telegram,
    find_chat_id,
)
from timer_engine import ROLLING_SECONDS, TimerEngine  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_invalid_numeric_values_use_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({
                "window_alpha": "broken",
                "weekly_reset_hour": {},
                "github_copilot": {"refresh_interval_sec": "broken"},
            }), encoding="utf-8")
            config = ConfigManager(path).load()
        self.assertEqual(config.window_alpha, 0.94)
        self.assertEqual(config.weekly_reset_hour, 0)
        self.assertEqual(config.github_copilot.refresh_interval_sec, 300)

    def test_notification_config_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"notifications": {
                "stale_after_sec": 1,
                "retry_attempts": 99,
                "retry_backoff_sec": -2,
            }}), encoding="utf-8")
            config = ConfigManager(path).load()
        self.assertEqual(config.notifications.stale_after_sec, 60)
        self.assertEqual(config.notifications.retry_attempts, 8)
        self.assertEqual(config.notifications.retry_backoff_sec, 0)

    def test_notification_endpoint_config_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"notifications": {
                "provider_hello_endpoints": {" github_copilot ": "http://bad", "x": ""},
                "provider_hello_timeout_sec": 99,
            }}), encoding="utf-8")
            config = ConfigManager(path).load()
        self.assertEqual(config.notifications.provider_hello_endpoints, {
            "github_copilot": "http://bad"
        })
        self.assertEqual(config.notifications.provider_hello_timeout_sec, 30)

    def test_telegram_setup_finds_chat_and_enables_notifications(self) -> None:
        responses = [
            Mock(status_code=200, json=lambda: {
                "ok": True,
                "result": [{"update_id": 8, "message": {
                    "chat": {"id": 123456, "first_name": "Test"}
                }}],
            }),
        ]
        with tempfile.TemporaryDirectory() as directory:
            manager = ConfigManager(Path(directory) / "config.json")
            chat_id, label = find_chat_id(
                "bot-token", request=Mock(side_effect=responses),
                sleep=lambda _: None, now=Mock(side_effect=[0, 0, 0, 0]),
            )
            configure_telegram(
                manager, "bot-token", chat_id, request=Mock(
                    return_value=Mock(status_code=200, json=lambda: {"ok": True})
                ),
            )
            config = manager.load()
        self.assertEqual((chat_id, label), ("123456", "Test"))
        self.assertTrue(config.notifications.enabled)
        self.assertEqual(config.notifications.telegram_chat_id, "123456")

    def test_telegram_setup_rejects_empty_token(self) -> None:
        with self.assertRaises(TelegramSetupError):
            find_chat_id("", wait_sec=1, sleep=lambda _: None)


class TimerTests(unittest.TestCase):
    def test_epoch_zero_is_respected(self) -> None:
        engine = TimerEngine(None, None, 0, 0, 0)
        engine.trigger_session(now=0)
        self.assertEqual(engine.rolling_reset_at, ROLLING_SECONDS)


class FetcherTests(unittest.TestCase):
    def test_sync_payload_contains_no_credentials(self) -> None:
        payload = state_payload(AggregatedQuotaState())
        self.assertNotIn("token", json.dumps(payload).lower())

    def test_antigravity_reader_uses_explicit_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"
            path.write_text(json.dumps({"models": {}}), encoding="utf-8")
            reader = AntigravityUsageReader(path)
            payload, source = reader.read()
            self.assertEqual(source, "cache")
            self.assertEqual(payload["models"], {})

    def test_copilot_user_quota_snapshots_preserve_models_and_prefer_premium(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "copilot_user_quota.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        snapshot = QuotaFetcher(AppConfig(), Mock())._parse_copilot(payload, {})
        self.assertEqual(snapshot.quota_percent, 65)
        self.assertEqual(snapshot.plan_tier, "individual")
        self.assertEqual(snapshot.reset_at, 1790812800)
        self.assertEqual([model.name for model in snapshot.models], [
            "chat", "completions", "premium_interactions",
        ])
        self.assertEqual(snapshot.models[0].remaining_percent, 100)
        self.assertTrue(snapshot.models[0].unlimited)
        self.assertEqual(snapshot.models[2].remaining, 65)

    def test_copilot_404_falls_back_to_identity(self) -> None:
        config = AppConfig()
        config.github_copilot.enabled = True
        config.github_copilot.github_token = "test-token"
        config.github_copilot.endpoint_url = "https://api.github.com/copilot_internal/v2/token"
        fetcher = QuotaFetcher(config, Mock())
        response = Mock(status_code=404, headers={})
        response.json.return_value = {"login": "test-user"}
        response.raise_for_status.return_value = None
        fetcher._request = Mock(return_value=response)
        snapshot = fetcher._fetch_github_copilot()
        self.assertEqual(snapshot.source, "remote")
        self.assertIsNone(snapshot.error)
        self.assertIn("test-user", snapshot.account_status)

    def test_copilot_token_endpoint_falls_back_to_quota_user_endpoint(self) -> None:
        config = AppConfig()
        config.github_copilot.enabled = True
        config.github_copilot.github_token = "test-token"
        config.github_copilot.endpoint_url = "https://api.github.com/copilot_internal/v2/token"
        fetcher = QuotaFetcher(config, Mock())
        token_response = Mock(status_code=200, headers={})
        token_response.json.return_value = {"token": "copilot-session-token"}
        quota_response = Mock(status_code=200, headers={})
        quota_response.json.return_value = {
            "breakdown": {"chat": {"quota": {"used": 25, "limit": 100}}},
            "plan": "individual",
        }
        fetcher._request = Mock(side_effect=[token_response, quota_response])
        snapshot = fetcher._fetch_github_copilot()
        self.assertEqual(snapshot.quota_percent, 75)
        self.assertEqual(fetcher._request.call_args_list[1].args[0], COPILOT_USER_ENDPOINT)

    def test_copilot_identity_without_quota_is_explicitly_unavailable(self) -> None:
        config = AppConfig()
        config.github_copilot.enabled = True
        config.github_copilot.github_token = "test-token"
        config.github_copilot.endpoint_url = COPILOT_USER_ENDPOINT
        fetcher = QuotaFetcher(config, Mock())
        user_response = Mock(status_code=200, headers={})
        user_response.json.return_value = {"login": "test-user"}
        identity_response = Mock(status_code=200, headers={})
        identity_response.json.return_value = {"login": "test-user"}
        fetcher._request = Mock(side_effect=[user_response, identity_response])
        snapshot = fetcher._fetch_github_copilot()
        self.assertIsNone(snapshot.quota_percent)
        self.assertIn("quota endpoint unavailable", snapshot.account_status)


class NotificationTests(unittest.TestCase):
    @staticmethod
    def state(reset_at: float, fetched_at: float = 1000, source: str = "remote",
              estimated: bool = False) -> AggregatedQuotaState:
        from quota_models import ProviderSnapshot
        return AggregatedQuotaState({
            "github_copilot": ProviderSnapshot(
                "github_copilot",
                weekly_reset_at=reset_at,
                fetched_at=fetched_at,
                source=source,
                estimated=estimated,
            ),
        }, fetched_at)

    def test_reset_event_is_deduplicated(self) -> None:
        sender = Mock()
        sender.send.return_value = True
        reminder = WeeklyQuotaReminder(NotificationDispatcher([sender]))
        state = self.state(900)
        self.assertTrue(reminder.process(state, now=1000))
        self.assertFalse(reminder.process(state, now=1001))
        sender.send.assert_called_once()

    def test_stale_or_estimated_data_does_not_send_provider_hello(self) -> None:
        sender = Mock()
        sender.send.return_value = True
        reminder = WeeklyQuotaReminder(NotificationDispatcher([sender]), stale_after_sec=30)
        self.assertFalse(reminder.process(self.state(900, fetched_at=900), now=1000))
        self.assertFalse(reminder.process(self.state(900, estimated=True), now=1000))
        sender.send.assert_not_called()

    def test_retryable_failure_retries_and_permanent_failure_stops(self) -> None:
        retryable = Mock()
        retryable.send.side_effect = [RetryableNotificationError(), True]
        permanent = Mock()
        permanent.send.side_effect = ValueError("bad request")
        dispatcher = NotificationDispatcher(
            [retryable, permanent], attempts=3, backoff_sec=0
        )
        self.assertTrue(dispatcher.send("hello"))
        self.assertEqual(retryable.send.call_count, 2)
        self.assertEqual(permanent.send.call_count, 1)

    def test_telegram_and_discord_payloads(self) -> None:
        response = Mock(status_code=200)
        telegram_request = Mock(return_value=response)
        discord_request = Mock(return_value=response)
        TelegramNotifier("bot", "chat", request=telegram_request).send("hello")
        DiscordNotifier("https://discord.test/hook", request=discord_request).send("hello")
        self.assertEqual(telegram_request.call_args.kwargs["json"],
                         {"chat_id": "chat", "text": "hello"})
        self.assertEqual(discord_request.call_args.kwargs["json"], {"content": "hello"})

    def test_from_config_gates_visible_hello_and_provider_action(self) -> None:
        config = AppConfig()
        config.notifications.enabled = True
        config.notifications.weekly_reminders = True
        config.notifications.provider_hello_endpoints = {
            "github_copilot": "https://example.test/hook"
        }
        reminder = WeeklyQuotaReminder.from_config(config.notifications)
        self.assertEqual(reminder.dispatcher.notifiers, [])
        self.assertIn("github_copilot", reminder.provider_actions)
        config.notifications.visible_hello = True
        config.notifications.telegram_bot_token = "bot"
        config.notifications.telegram_chat_id = "chat"
        self.assertEqual(
            len(WeeklyQuotaReminder.from_config(config.notifications).dispatcher.notifiers), 1
        )

    def test_provider_action_runs_once_only_after_eligible_reset(self) -> None:
        action = Mock()
        action.send.return_value = True
        reminder = WeeklyQuotaReminder(
            NotificationDispatcher([]),
            provider_actions={"github_copilot": action},
        )
        self.assertTrue(reminder.process(self.state(900), now=1000))
        self.assertFalse(reminder.process(self.state(900), now=1001))
        action.send.assert_called_once()

    def test_provider_hello_payload_is_non_causal_and_bounded(self) -> None:
        response = Mock(status_code=200)
        request = Mock(return_value=response)
        ProviderHelloNotifier(
            "https://example.test/hook", "github_copilot", timeout_sec=4, request=request
        ).send("github_copilot post-reset hello")
        self.assertEqual(request.call_args.kwargs["timeout"], 4)
        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["event"], "post-reset hello")
        self.assertNotIn("token", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main()
