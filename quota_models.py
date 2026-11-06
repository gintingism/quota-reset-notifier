from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuotaStatus:
    name: str
    remaining_percent: float | None = None
    reset_at: float | None = None
    remaining: float | None = None
    entitlement: float | None = None
    unlimited: bool | None = None
    used: float | None = None


@dataclass(frozen=True)
class ProviderSnapshot:
    provider: str
    models: tuple[QuotaStatus, ...] = ()
    quota_percent: float | None = None
    reset_at: float | None = None
    rolling_reset_at: float | None = None
    weekly_reset_at: float | None = None
    plan_tier: str = "Unknown"
    account_status: str = "Not connected"
    fetched_at: float = 0.0
    source: str = "local"
    error: str | None = None
    estimated: bool = False


@dataclass(frozen=True)
class AggregatedQuotaState:
    providers: dict[str, ProviderSnapshot] = field(default_factory=dict)
    fetched_at: float = 0.0
