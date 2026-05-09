# CARTE Credit Auto-Claim Bot

Auto-claim bot for [carte.gg](https://carte.gg) credits. Uses Manifold OAuth tokens from browser localStorage.

## Setup

```bash
pip install requests
```

## Usage

1. Get `manideck-auth` token from browser (F12 → Application → Local Storage → carte.gg → `manideck-auth`).
2. Paste when prompted — refresh token auto-managed.
3. Run:

```bash
python carte_bot.py
```

## Features

- Auto-refresh token before expiry
- Auto-claim when credits > 0
- `dripIntervalSeconds: 300` (5 min) claim cycle
- Credits capped at 50

## Security

⚠️ **Never commit session files.** Session stored in `~/.carte-bot/session.json`.

---

*bot by billy (ethjup)*
