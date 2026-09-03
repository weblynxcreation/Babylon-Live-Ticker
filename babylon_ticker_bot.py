import os
import json
import asyncio
import logging
from typing import Optional

import aiohttp
import discord
from discord import Embed
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
TOP_N = int(os.getenv("TOP_N", "15"))
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "60"))

# CapitalRift integration (addition, not override)
CAPITAL_RIFT_ENABLED = os.getenv("CAPITAL_RIFT_ENABLED", "false").lower() in ("1", "true", "yes")
CAPITAL_RIFT_REFRESH_SECONDS = int(os.getenv("CAPITAL_RIFT_REFRESH_SECONDS", "57"))
CAPITAL_RIFT_URL = os.getenv("CAPITAL_RIFT_URL", "https://capitalrift.com/api/access/status")

STATE_FILE = "ticker_state.json"
BABYLON_URL = "https://holdings.thebabylon.hu/api/v1/companies"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("babylon-ticker")

intents = discord.Intents.none()
client = discord.Client(intents=intents)

# Simple state persistence
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Backwards-compat: old format had message_id
            if "message_id" in data and "babylon_message_id" not in data:
                data["babylon_message_id"] = data.pop("message_id")
            return data
    except Exception:
        return {}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

async def fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> Optional[dict]:
    try:
        async with session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.json()
    except Exception as e:
        log.warning("Failed fetching %s: %s", url, e)
        return None

def build_babylon_embed(companies: list) -> Embed:
    embed = Embed(title="Top Companies — Babylon Holdings")
    if not companies:
        embed.description = "(no data)"
        return embed

    for c in companies[:TOP_N]:
        name = c.get("name") or c.get("ticker") or "Unknown"
        price = c.get("sharePrice")
        price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else str(price)
        change = c.get("trendPct")
        change_str = f" ({change:+.2f}%)" if isinstance(change, (int, float)) else ""
        embed.add_field(name=name, value=f"{price_str}{change_str}", inline=True)
    embed.set_footer(text=f"Updated every {REFRESH_SECONDS}s")
    return embed

def _find_commodities(data: dict, symbols: set) -> dict:
    """Try to locate commodity entries matching symbols in a few common shapes.
    Returns a mapping symbol -> entry (dict).
    """
    found = {}

    # common container keys
    for key in ("commodities", "resources", "markets", "prices", "market"):
        val = data.get(key)
        if isinstance(val, list):
            for item in val:
                if not isinstance(item, dict):
                    continue
                sym = (item.get("symbol") or item.get("ticker") or item.get("id") or "").upper()
                if sym in symbols:
                    found[sym] = item
        elif isinstance(val, dict):
            for sym in symbols:
                if sym in val:
                    found[sym] = val[sym]

    # direct top-level symbol keys
    for sym in symbols:
        if sym in data and isinstance(data[sym], dict):
            found[sym] = data[sym]

    # shallow recursive search to catch nested dicts with symbol fields
    def recurse(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, dict):
                    key_up = (k or "").upper()
                    if key_up in symbols and key_up not in found:
                        found[key_up] = v
                recurse(v)
        elif isinstance(o, list):
            for it in o:
                recurse(it)
    recurse(data)
    return found


def _fmt_price(v):
    try:
        if isinstance(v, (int, float)):
            return f"{v:,.2f}"
        return str(v)
    except Exception:
        return str(v)


def build_capitalrift_embed(status: dict) -> Embed:
    embed = Embed(title="CapitalRift Status")
    if not status:
        embed.description = "(no data)"
        return embed

    # playersOnline
    po = status.get("playersOnline")
    if po is not None:
        embed.add_field(name="Players Online", value=str(po), inline=False)

    # betaPlayers -> show top netWorth entries when available
    bp = status.get("betaPlayers")
    if isinstance(bp, list) and bp:
        # sort by netWorth if present
        players = [p for p in bp if isinstance(p, dict)]
        players.sort(key=lambda x: x.get("netWorth") or 0, reverse=True)
        lines = []
        for p in players[:5]:
            name = p.get("name") or p.get("id") or "player"
            nw = p.get("netWorth")
            lines.append(f"{name}: ${_fmt_price(nw)}")
        embed.add_field(name="Top Beta Players (netWorth)", value="\n".join(lines), inline=False)
    elif isinstance(bp, dict) and "netWorth" in bp:
        embed.add_field(name="BetaPlayers netWorth", value=f"${_fmt_price(bp.get('netWorth'))}", inline=False)

    # gdp24h
    if "gdp24h" in status:
        embed.add_field(name="GDP 24h", value=str(status.get("gdp24h")), inline=False)

    # Commodities of interest
    symbols = {"CNC", "ORE", "CRN", "WD", "SHT", "ONI", "PLK", "BAR", "NLS", "STR"}
    found = _find_commodities(status, symbols)

    if found:
        for sym in ["CNC", "ORE", "CRN", "WD", "SHT", "ONI", "PLK", "BAR", "NLS", "STR"]:
            ent = found.get(sym)
            if not ent:
                continue
            # try common fields
            price = ent.get("price") if isinstance(ent, dict) else None
            if price is None:
                price = ent.get("lastPrice") or ent.get("value") or ent.get("rate")
            units = ent.get("units") or ent.get("unit") or ent.get("quantity")
            parts = []
            if price is not None:
                parts.append(f"price: { _fmt_price(price) }")
            if units is not None:
                parts.append(f"units: {units}")
            if parts:
                embed.add_field(name=sym, value=", ".join(parts), inline=True)

    # If nothing useful found, show a compact JSON snapshot (truncated)
    if len(embed.fields) == 0:
        embed.description = f"```\n{json.dumps(status, indent=2)[:1900]}\n```"

    embed.set_footer(text=f"Polled every {CAPITAL_RIFT_REFRESH_SECONDS}s")
    return embed

async def ensure_message(channel: discord.abc.Messageable, message_id: Optional[int]) -> discord.Message:
    if message_id:
        try:
            msg = await channel.fetch_message(message_id)
            return msg
        except Exception:
            pass
    # Create a placeholder message
    msg = await channel.send("Initializing ticker...")
    return msg

@client.event
async def on_ready():
    log.info("Logged in as %s", client.user)
    state = load_state()
    channel = await client.fetch_channel(DISCORD_CHANNEL_ID)

    # Babylon message
    babylon_msg_id = state.get("babylon_message_id")
    babylon_msg = await ensure_message(channel, babylon_msg_id)
    state["babylon_message_id"] = babylon_msg.id
    save_state(state)

    # Start background tasks
    client.loop.create_task(babylon_loop(channel, babylon_msg))

    if CAPITAL_RIFT_ENABLED:
        # Use separate message for CapitalRift to keep them additive
        cr_msg_id = state.get("capitalrift_message_id")
        cr_msg = await ensure_message(channel, cr_msg_id)
        state["capitalrift_message_id"] = cr_msg.id
        save_state(state)
        client.loop.create_task(capitalrift_loop(channel, cr_msg))

async def babylon_loop(channel: discord.TextChannel, message: discord.Message):
    async with aiohttp.ClientSession() as session:
        while True:
            data = await fetch_json(session, BABYLON_URL)
            companies = []
            if isinstance(data, list):
                companies = sorted(data, key=lambda x: x.get("sharePrice") or 0, reverse=True)
            elif isinstance(data, dict) and "companies" in data and isinstance(data["companies"], list):
                companies = sorted(data["companies"], key=lambda x: x.get("sharePrice") or 0, reverse=True)

            embed = build_babylon_embed(companies)
            try:
                await message.edit(content=None, embed=embed)
            except Exception as e:
                log.warning("Failed to edit babylon message: %s", e)
            await asyncio.sleep(REFRESH_SECONDS)

async def capitalrift_loop(channel: discord.TextChannel, message: discord.Message):
    async with aiohttp.ClientSession() as session:
        while True:
            status = await fetch_json(session, CAPITAL_RIFT_URL)
            embed = build_capitalrift_embed(status)
            try:
                await message.edit(content=None, embed=embed)
            except Exception as e:
                log.warning("Failed to edit capitalrift message: %s", e)
            await asyncio.sleep(CAPITAL_RIFT_REFRESH_SECONDS)

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID == 0:
        log.error("DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set in the environment (.env)")
        raise SystemExit(1)
    client.run(DISCORD_BOT_TOKEN)
