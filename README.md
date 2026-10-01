# TeleGuard

An anti-spam and moderation bot for Telegram groups: it stops join bots with a CAPTCHA, scores new
members for risk, and filters flooding and spam — so admins don't have to babysit the group.

![Example of the messages the bot sends](docs/example-messages.png)

*Example of the messages the bot posts in a group.*

## What it does

**On join** — new members are muted until they pass a quick CAPTCHA (bots almost never do). Before that,
each member gets a **risk score** from their profile, and risky ones get a harder challenge:

- no profile photo, no username
- links, @handles or spam keywords in the name
- mixed scripts (e.g. Cyrillic letters faking Latin ones)
- the account's **datacenter** (DC1–DC5), derived from the profile photo — a weak, optional hint

![New-member risk score](docs/risk-scores.png)

**On every message** — an anti-flood limit and a spam filter (links or forwarded channel posts from new
users, spam phrases, mass mentions). Offenders are deleted and warned; enough warnings = a ban.

![How it works](docs/pipeline.svg)

**Admin commands** (reply to a message): `/ban`, `/mute`, `/warn`.

## Setup

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill it in
```

1. Create a bot with [@BotFather](https://t.me/BotFather) → `TELEGRAM_BOT_TOKEN`.
2. Add it to your group **as an admin** with *ban users*, *delete messages* and *restrict members*.
3. Disable BotFather's *Group Privacy* so it can read messages.

```bash
python -m teleguard
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | – | Bot token |
| `CAPTCHA_TIMEOUT` | `60` | Seconds to solve the join challenge |
| `FLOOD_MAX` / `FLOOD_SECONDS` | `5` / `5` | Messages per window before a mute |
| `WARN_LIMIT` | `3` | Warnings before an automatic ban |
| `RISK_THRESHOLD` | `4` | Risk score treated as suspicious |
| `SUSPICIOUS_DATACENTERS` | – | DCs to flag, e.g. `4 5` (weak signal, off by default) |

## Tests

```bash
pip install pytest
pytest
```

The moderation logic (risk, spam, anti-flood, datacenter decoding) is pure and unit-tested; the charts
above are generated from that same code.

## Tech stack

Python · python-telegram-bot · asyncio

## License

[MIT](LICENSE)
