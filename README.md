# Babylon Holdings — Live Ticker Discord Bot

Posts a single embed in a channel of your choice listing the top companies
from `https://holdings.thebabylon.hu/api/v1/companies`, sorted by share
price, and keeps editing that **same message** every `REFRESH_SECONDS`
(default 60s) — so it updates live without spamming the channel.

## 1. Create the Discord bot

1. Go to https://discord.com/developers/applications → **New Application**.
2. Go to the **Bot** tab → **Add Bot** → copy the **Token** (this is your `DISCORD_BOT_TOKEN`).
3. Still on the Bot tab, make sure these are OFF (not needed here): Presence Intent, Server Members Intent, Message Content Intent.
4. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`
   - Open the generated URL and invite the bot to your server.
5. In Discord, enable **Developer Mode** (User Settings → Advanced), then right-click the channel you want tickers posted in → **Copy Channel ID**. This is your `DISCORD_CHANNEL_ID`.

## 2. Install & configure

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID
```

## 3. Run it

```bash
python babylon_ticker_bot.py
```

The bot will log in, post an embed of the top 15 companies by share price,
and refresh it every 60 seconds. Both `TOP_N` and `REFRESH_SECONDS` are
configurable in `.env`.

It remembers the message it's editing in `ticker_state.json` — as long as
that file sticks around between restarts, it'll keep editing the same
message instead of posting a new one.

## Notes / things you might want to tweak

- **Rate limits**: Discord allows editing a message roughly once every few
  seconds without issue; a 60s refresh is very safe. Don't drop below
  ~10-15s.
- **Sorting/filtering**: `build_embed()` in `babylon_ticker_bot.py` sorts by
  `sharePrice` — easy to change to `trendPct` (biggest gainers/losers) or
  `netWorth` if you'd rather track those.
- **Multiple channels / servers**: currently posts to one channel. If you
  want it in multiple channels, the loop can be extended to track a message
  ID per channel.
- **Hosting**: this needs to run continuously somewhere (a small VPS,
  Railway, Render, a Raspberry Pi, etc.) — running it only on your own
  machine means it stops updating when your machine is off.

## 4. Optional: CapitalRift status streamer (addition)

An optional addition fetches and streams data from https://capitalrift.com/api/access/status and edits a second message in the same channel so it does not override the Babylon embed.

Environment variables (add to your .env):

- CAPITAL_RIFT_ENABLED=true  # enable the CapitalRift polling (default: false)
- CAPITAL_RIFT_URL=https://capitalrift.com/api/access/status
- CAPITAL_RIFT_REFRESH_SECONDS=57  # poll interval in seconds (default: 57)

When enabled, the bot will create / edit a second message in the configured channel with CapitalRift status and poll it every CAPITAL_RIFT_REFRESH_SECONDS (default 57s). This is additive — it will not replace the Babylon ticker message.
