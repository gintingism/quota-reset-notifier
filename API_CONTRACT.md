# Quota sync JSON contract

The desktop app sends versioned snapshots to the optional Cloudflare Worker.
The relay stores only the latest normalized snapshot in KV and never stores
GitHub or Antigravity credentials.

```json
{
  "version": 1,
  "fetched_at": 1730000000,
  "providers": {
    "github_copilot": {
      "quota_percent": 65,
      "reset_at": 1790812800,
      "models": [{"name": "premium_interactions", "remaining_percent": 65}],
      "estimated": false
    }
  }
}
```

`POST /api/quota/sync` writes the snapshot and `GET /api/quota/latest` returns
it. Both endpoints require `X-Auth-Token`; clients should treat missing or
stale snapshots as unavailable. This contract is intended for future mobile
or web clients and does not imply an undocumented provider API.
