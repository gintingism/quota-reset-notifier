from __future__ import annotations

import json
from typing import Any

import requests

from config_manager import SyncRelayConfig
from quota_models import AggregatedQuotaState


def state_payload(state: AggregatedQuotaState) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for name, snapshot in state.providers.items():
        providers[name] = {
            "models": [
                {
                    "name": model.name,
                    "remaining_percent": model.remaining_percent,
                    "reset_at": model.reset_at,
                    "remaining": model.remaining,
                    "entitlement": model.entitlement,
                    "unlimited": model.unlimited,
                    "used": model.used,
                }
                for model in snapshot.models
            ],
            "quota_percent": snapshot.quota_percent,
            "reset_at": snapshot.reset_at,
            "rolling_reset_at": snapshot.rolling_reset_at,
            "weekly_reset_at": snapshot.weekly_reset_at,
            "plan_tier": snapshot.plan_tier,
            "account_status": snapshot.account_status,
            "fetched_at": snapshot.fetched_at,
            "source": snapshot.source,
            "error": snapshot.error,
            "estimated": snapshot.estimated,
        }
    return {"version": 1, "fetched_at": state.fetched_at, "providers": providers}


def sync_state(config: SyncRelayConfig, state: AggregatedQuotaState) -> bool:
    if not config.enabled or not config.base_url or not config.auth_token:
        return False
    url = config.base_url.rstrip("/") + "/api/quota/sync"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json", "X-Auth-Token": config.auth_token},
        data=json.dumps(state_payload(state), ensure_ascii=True),
        timeout=10,
    )
    response.raise_for_status()
    return True
