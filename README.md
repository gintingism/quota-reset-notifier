# Quota Reset Notifier

Quota Reset Notifier is a small Windows desktop app for watching quota data from
Google Antigravity and GitHub Copilot. It keeps the current status visible in a
floating widget and can send a Telegram or Discord message when a provider
reports that its weekly reset time has passed.

The app does not manufacture quota numbers. When a provider cannot supply a
fresh, confirmed value, the widget shows that the value is unavailable instead
of presenting an estimate as fact.

## What it does

- Shows rolling five-hour and weekly quota information in a desktop widget.
- Runs from the Windows system tray and supports a docked layout.
- Stores window, timer, and provider settings in
  `%APPDATA%\AIQuotaWidget\config.json`.
- Reads Antigravity through the configured source or the official
  `antigravity /usage` command when no endpoint is configured.
- Reads GitHub Copilot through the configured endpoint. The default internal
  endpoint is undocumented and may change.
- Sends weekly reset reminders to Telegram, Discord, or both.
- Deduplicates reset events and retries temporary notification failures.
- Rejects stale, estimated, cached, or errored provider data for reminders.
- Keeps provider credentials out of relay payloads and application logs.

## Current limitations

Quota providers expose different information, so the app cannot promise one
identical data source for every account.

- GitHub documents individual AI Credits as a monthly allowance. Its documented
  usage APIs focus on organization and enterprise reporting. A live individual
  quota may therefore be unavailable.
- Antigravity documents `/usage` and `/quota` as CLI surfaces, but it does not
  currently provide a stable public quota API for this app to depend on.
- A weekly reminder is sent only when the provider reports a reset timestamp
  and the data is fresh. The local weekly schedule is useful for display, not
  proof that the provider reset.
- The optional provider-specific post-reset callback is just an HTTPS POST to
  an endpoint you control. It does not reset provider quota and is disabled
  unless you configure it.

## Run from source

PowerShell:

```powershell
git clone https://github.com/gintingism/quota-reset-notifier.git
cd quota-reset-notifier
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The app tries `gh auth token` first when it auto-configures GitHub Copilot, then
falls back to the local GitHub hosts file. It does not print the token.

To run the one-time GitHub configuration without opening the widget:

```powershell
python auto_configure_github.py
```

The script does not replace an existing token. To force a refresh:

```powershell
python -c "from config_manager import ConfigManager; ConfigManager().auto_configure_github_token(force=True)"
```

## Configure providers

Open **Settings** from the tray menu or by right-clicking the widget.

### Google Antigravity

You can provide an endpoint, session token, and cookies when your local setup
needs them. If the endpoint is empty, the app tries:

```powershell
antigravity /usage
```

If that command is not available, the app may use the explicit local cache
configured by the provider adapter. Cached data is marked and is not eligible
to trigger a reset notification.

### GitHub Copilot

Enable the provider and enter a GitHub token, or let the app discover one with
the GitHub CLI. You can change the Copilot endpoint and editor version in
Settings. If the response contains identity data but no usable quota, the app
shows `--%` and explains that quota is unavailable.

## Configure notifications

Open **Settings > Weekly notifications**.

The app requires both `notifications.enabled` and
`notifications.weekly_reminders` before it processes reset events.

### Telegram

Create a bot with [@BotFather](https://t.me/BotFather), start a conversation
with it, then enter the bot token and destination chat ID in Settings. The app
uses Telegram's `sendMessage` method and sends only the reminder text.

### Discord

Create an incoming webhook for the target channel under the channel's
**Integrations** settings. Paste the webhook URL into Settings. The app sends a
small JSON payload containing the reminder text.

### Visible post-reset message

Turn on **Visible post-reset hello** if you want the reminder text to be sent
to the configured Telegram or Discord destinations. This message is a local
notification about a provider-reported reset. It is not a request that causes
the reset.

Provider-specific callbacks are separate. If you use them, configure an HTTPS
endpoint for the provider and keep the endpoint under your control. The app
does not send GitHub tokens, Antigravity tokens, cookies, or webhook secrets in
the callback payload.

## Configuration file

`config.example.json` shows the available fields. Copy it only when you want
to prepare an initial configuration manually. The active file is created
automatically at:

```text
%APPDATA%\AIQuotaWidget\config.json
```

The app migrates the older flat Antigravity fields when it reads the file.
Treat this file as sensitive because it can contain provider credentials and
notification secrets. Do not commit or share it.

## Build the Windows executable

```powershell
python -m pip install -r requirements.txt
python build.py
```

The build produces `dist\QuotaResetNotifier.exe`. Runtime settings remain under
`%APPDATA%\AIQuotaWidget`; they are not written into the temporary bundle
directory.

## Test and checks

Run the unit tests and basic source checks from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
git diff --check
```

## Relay and future clients

The optional Cloudflare KV relay and its normalized JSON contract are documented
in [worker/README.md](worker/README.md) and
[API_CONTRACT.md](API_CONTRACT.md). The relay receives normalized snapshots,
not provider credentials.

## Sources

- [GitHub: About repository README files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)
- [GitHub: Copilot billing for individuals](https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing)
- [GitHub: Copilot usage metrics](https://docs.github.com/en/copilot/concepts/copilot-metrics)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Discord webhooks](https://docs.discord.com/developers/platform/webhooks)
- [Antigravity CLI usage](https://antigravity.google/docs/cli/commands/usage)

## License

This project is licensed under the
[GNU General Public License v3.0 or later](LICENSE).

You may use, study, modify, and redistribute the project under the terms of
that license. If you distribute a modified version, keep the license and
source-availability requirements that apply to GPL-covered software.

The dependencies listed in `requirements.txt` remain under their own licenses.
