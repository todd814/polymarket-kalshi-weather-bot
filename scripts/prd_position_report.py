#!/usr/bin/env python3
"""
C-137 Production Position & Weather Decision Reporter
=====================================================
Queries production `tradingbot.db` (and live NWS ASOS station observations) to show:
  1. WHY each position was bought (entry ensemble forecast, edge, model prob, price, contracts)
  2. CURRENT weather state (latest 82-member ensemble forecast + live NWS airport observed high)
  3. ESTIMATED OUTCOME (Win Probability, Ratchet Lock status, Expected Payout & Net Profit)

Usage:
  # Run directly on production VM (or local DB):
  ./venv/bin/python scripts/prd_position_report.py

  # Include already-settled historical trades:
  ./venv/bin/python scripts/prd_position_report.py --all

  # Run from local Mac against live GCP production VM (`weather-bot-free`):
  ./venv/bin/python scripts/prd_position_report.py --remote
"""
import argparse
import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


CITY_PREFIX_MAP = {
    "KXHIGHNY": ("nyc", "New York (KNYC)"),
    "KXHIGHCHI": ("chicago", "Chicago (KORD)"),
    "KXHIGHMIA": ("miami", "Miami (KMIA)"),
    "KXHIGHLAX": ("los_angeles", "Los Angeles (KLAX)"),
    "KXHIGHDEN": ("denver", "Denver (KDEN)"),
    "KXHIGHAUS": ("austin", "Austin (KATT)"),
    "KXHIGHTHOU": ("houston", "Houston (KIAH)"),
    "KXHIGHDCA": ("washington_dc", "Wash DC (KDCA)"),
    "KXHIGHBOS": ("boston", "Boston (KBOS)"),
    "KXHIGHPHIL": ("philadelphia", "Philly (KPHL)"),
}


def parse_ticker_info(ticker: str):
    """Parse city_key, target_date, and human-readable strike from Kalshi ticker."""
    prefix = ticker.split("-")[0] if "-" in ticker else ticker
    city_key, city_label = CITY_PREFIX_MAP.get(prefix, ("unknown", prefix))

    target_dt = None
    m_dt = re.search(r"-(\d{2}[A-Z]{3}\d{2})-", ticker.upper())
    if m_dt:
        try:
            target_dt = datetime.strptime(m_dt.group(1), "%y%b%d").date()
        except ValueError:
            pass

    strike_desc = ticker.split("-")[-1] if "-" in ticker else ticker
    m_strike = re.search(r"-([BT])(-?\d+(?:\.\d+)?)$", ticker.upper())
    if m_strike:
        kind, val_s = m_strike.group(1), float(m_strike.group(2))
        if kind == "B":
            low_b = int(val_s - 0.5)
            high_b = int(val_s + 0.5)
            strike_desc = f"{low_b}-{high_b}°F Bracket"
        else:
            strike_desc = f"Threshold {val_s:g}°F"

    return city_key, city_label, target_dt, strike_desc


def extract_ensemble_summary(reasoning: str) -> str:
    """Pull 'Ensemble: XX.XF +/- Y.YF (82m...)' and strike rule out of signal.reasoning."""
    if not reasoning:
        return "N/A"
    m_ens = re.search(r"Ensemble:\s*([0-9.]+F\s*\+/-\s*[0-9.]+F\s*\([^)]+\))", reasoning)
    m_rule = re.search(r"\b(high|low)\s+(above|below|between)\s+([0-9.-]+F)", reasoning, re.IGNORECASE)
    parts = []
    if m_rule:
        parts.append(f"{m_rule.group(1)} {m_rule.group(2)} {m_rule.group(3)}")
    if m_ens:
        parts.append(f"Ens {m_ens.group(1)}")
    return " | ".join(parts) if parts else reasoning[:75]


async def fetch_live_obs_by_city(city_keys_and_dates: set) -> dict:
    """Fetch current NWS ASOS observed high/low for active same-day cities."""
    obs_map = {}
    try:
        import logging
        logging.getLogger("trading_bot").setLevel(logging.CRITICAL)
        from backend.data.weather import fetch_nws_observed_temperature
        for city_key, target_dt in city_keys_and_dates:
            if not city_key or city_key == "unknown" or target_dt is None:
                continue
            try:
                obs = await fetch_nws_observed_temperature(city_key, target_dt)
                if obs and obs.get("high") is not None:
                    obs_map[(city_key, target_dt)] = obs
            except Exception:
                pass
    except Exception:
        pass
    return obs_map


def query_positions(db_path: str, include_settled: bool = False) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where_settled = "" if include_settled else "AND t.settled = 0"
    sql = f"""
    WITH latest_signal AS (
        SELECT
            s.market_ticker,
            s.timestamp AS latest_scan_utc,
            s.direction AS latest_sig_dir,
            s.model_probability AS latest_model_yes_prob,
            s.market_price AS latest_mkt_yes_price,
            s.edge AS latest_edge,
            s.reasoning AS latest_reasoning,
            ROW_NUMBER() OVER (PARTITION BY s.market_ticker ORDER BY s.timestamp DESC, s.id DESC) AS rn
        FROM signals s
        WHERE s.market_type = 'weather'
    ),
    entry_signal_fallback AS (
        SELECT
            s.market_ticker,
            s.reasoning AS first_reasoning,
            ROW_NUMBER() OVER (PARTITION BY s.market_ticker ORDER BY s.timestamp ASC, s.id ASC) AS rn
        FROM signals s
        WHERE s.market_type = 'weather'
    )
    SELECT
        t.id,
        t.market_ticker,
        t.direction,
        t.entry_price,
        t.size,
        t.timestamp AS entry_utc,
        t.settled,
        t.result,
        t.pnl,
        t.model_probability AS entry_model_yes_prob,
        t.market_price_at_entry AS entry_mkt_yes_prob,
        t.edge_at_entry,
        COALESCE(es.reasoning, esf.first_reasoning) AS entry_reasoning,
        ls.latest_scan_utc,
        ls.latest_model_yes_prob,
        ls.latest_mkt_yes_price,
        ls.latest_edge,
        ls.latest_reasoning
    FROM trades t
    LEFT JOIN signals es ON es.id = t.signal_id
    LEFT JOIN entry_signal_fallback esf ON esf.market_ticker = t.market_ticker AND esf.rn = 1
    LEFT JOIN latest_signal ls ON ls.market_ticker = t.market_ticker AND ls.rn = 1
    WHERE t.is_paper = 0
      AND t.market_type = 'weather'
      {where_settled}
    ORDER BY t.settled ASC, t.id DESC
    """
    rows = [dict(r) for r in cur.execute(sql).fetchall()]

    state_row = cur.execute("SELECT bankroll, total_trades, winning_trades, total_pnl FROM bot_state LIMIT 1").fetchone()
    state = dict(state_row) if state_row else {}
    conn.close()
    return rows, state


async def build_and_print_report(db_path: str, include_settled: bool = False, as_json: bool = False):
    rows, state = query_positions(db_path, include_settled=include_settled)
    today_est = datetime.now(ZoneInfo("America/New_York")).date()

    # Collect same-day unsettled city/date pairs to query live NWS ASOS station highs
    active_city_dates = set()
    for r in rows:
        if r["settled"]:
            continue
        city_key, _, target_dt, _ = parse_ticker_info(r["market_ticker"])
        if target_dt is not None and target_dt == today_est:
            active_city_dates.add((city_key, target_dt))

    obs_map = await fetch_live_obs_by_city(active_city_dates)

    enriched = []
    total_open_risk = 0.0
    total_est_ev_pnl = 0.0
    total_if_all_expected_win = 0.0

    for r in rows:
        ticker = r["market_ticker"]
        held_dir = (r["direction"] or "yes").lower()
        entry_price = float(r["entry_price"] or 0.5)
        size = float(r["size"] or 0.0)
        contracts = round(size / entry_price, 2) if entry_price > 0 else 0.0
        gross_payout = round(contracts * 1.0, 2)
        net_win_profit = round(gross_payout - size, 2)

        entry_yes_p = float(r["entry_model_yes_prob"] if r["entry_model_yes_prob"] is not None else 0.5)
        entry_win_prob = entry_yes_p if held_dir == "yes" else (1.0 - entry_yes_p)

        curr_yes_p = float(
            r["latest_model_yes_prob"]
            if r["latest_model_yes_prob"] is not None
            else entry_yes_p
        )
        curr_win_prob = curr_yes_p if held_dir == "yes" else (1.0 - curr_yes_p)

        curr_mkt_yes = (
            float(r["latest_mkt_yes_price"])
            if r["latest_mkt_yes_price"] is not None
            else float(r["entry_mkt_yes_prob"] or entry_price)
        )
        curr_side_mark = curr_mkt_yes if held_dir == "yes" else round(1.0 - curr_mkt_yes, 4)

        city_key, city_label, target_dt, strike_desc = parse_ticker_info(ticker)
        obs = obs_map.get((city_key, target_dt))
        observed_high_f = obs.get("high") if obs else None

        entry_wx = extract_ensemble_summary(r["entry_reasoning"])
        latest_wx = extract_ensemble_summary(r["latest_reasoning"] or r["entry_reasoning"])

        # Determine winning rule and estimated outcome
        if r["settled"]:
            verdict = f"SETTLED {str(r['result']).upper()} ({r['pnl']:+.2f})"
            horizon_bucket = "SETTLED"
        else:
            total_open_risk += size
            ev_pnl = curr_win_prob * net_win_profit - (1.0 - curr_win_prob) * size
            total_est_ev_pnl += ev_pnl
            if curr_win_prob >= 0.50:
                total_if_all_expected_win += net_win_profit

            if target_dt and target_dt < today_est:
                horizon_bucket = f"OUTCOME PENDING ({target_dt})"
            elif target_dt and target_dt > today_est:
                horizon_bucket = f"TOMORROW T+1 ({target_dt})"
            else:
                horizon_bucket = f"TODAY T+0 ({target_dt})"

            if curr_win_prob >= 0.90 or (0.85 <= curr_side_mark < 1.0):
                verdict = f"LOCKED WIN ({curr_win_prob:.0%} model)"
            elif curr_win_prob >= 0.75:
                verdict = f"EST. WIN - STRONG ({curr_win_prob:.0%})"
            elif curr_win_prob >= 0.55:
                verdict = f"EST. WIN - LEAN ({curr_win_prob:.0%})"
            elif curr_win_prob >= 0.45:
                verdict = f"TOSS-UP ({curr_win_prob:.0%})"
            else:
                verdict = f"AT RISK ({curr_win_prob:.0%})"

        item = {
            "id": r["id"],
            "ticker": ticker,
            "city": city_label,
            "target_date": str(target_dt) if target_dt else "N/A",
            "bucket": horizon_bucket,
            "side": held_dir.upper(),
            "strike": strike_desc,
            "contracts": contracts,
            "entry_price": entry_price,
            "risked_usd": size,
            "payout_if_win_usd": gross_payout,
            "net_profit_if_win_usd": net_win_profit,
            "entry_win_prob": round(entry_win_prob, 4),
            "entry_edge": round(float(r["edge_at_entry"] or 0.0), 4),
            "current_win_prob": round(curr_win_prob, 4),
            "current_side_mark": curr_side_mark,
            "nws_observed_high_f": round(observed_high_f, 1) if observed_high_f is not None else None,
            "why_bought": entry_wx,
            "current_weather": latest_wx,
            "estimated_outcome": verdict,
        }
        enriched.append(item)

    if as_json:
        print(json.dumps({"state": state, "positions": enriched}, indent=2))
        return

    print("=" * 124)
    print(
        f" C-137 PRODUCTION WEATHER POSITION & DECISION REPORT | "
        f"Cash: ${state.get('bankroll', 0.0):.2f} | "
        f"Open Risk: ${total_open_risk:.2f} | "
        f"Realized P&L: ${state.get('total_pnl', 0.0):+.2f}"
    )
    print("=" * 124)
    print(
        f"{'ID':>3}  {'TICKER':<24} {'SIDE':<4} {'CONTR':>6} {'ENTRY':>6} {'RISK':>6} "
        f"{'WIN+$':>7} {'ENT_P':>5} {'CUR_P':>5} {'NWS_HI':>7}  {'ESTIMATED OUTCOME':<26}"
    )
    print("-" * 124)

    for p in enriched:
        nws_s = f"{p['nws_observed_high_f']:.1f}F" if p["nws_observed_high_f"] is not None else "  --  "
        print(
            f"#{p['id']:<2}  {p['ticker']:<24} {p['side']:<4} {p['contracts']:>5.1f}x "
            f"${p['entry_price']:>4.2f} ${p['risked_usd']:>5.2f} "
            f"+${p['net_profit_if_win_usd']:>5.2f} {p['entry_win_prob']:>4.0%} "
            f"{p['current_win_prob']:>4.0%} {nws_s:>7}  {p['estimated_outcome']:<26}"
        )
        print(f"     ├─ WHY BOUGHT ({p['bucket']}): Edge {p['entry_edge']:+.1%} | {p['why_bought']}")
        if p["current_weather"] != p["why_bought"]:
            print(f"     └─ LATEST WX SCAN          : Mark ${p['current_side_mark']:.2f}  | {p['current_weather']}")
        else:
            print(f"     └─ CURRENT MARKET MARK     : ${p['current_side_mark']:.2f} on {p['side']} ({p['strike']})")
        print("-" * 124)

    print(
        f" SUMMARY: {len(enriched)} position(s) | Total Deployed: ${total_open_risk:.2f} | "
        f"Model Expected EV: ${total_est_ev_pnl:+.2f} | "
        f"Net Profit if Favored (>=50%) Positions Win: +${total_if_all_expected_win:.2f}"
    )
    print("=" * 124)


def main():
    parser = argparse.ArgumentParser(description="Query production weather trade decisions and estimated outcomes.")
    parser.add_argument("--db", default=str(ROOT_DIR / "tradingbot.db"), help="Path to SQLite tradingbot.db")
    parser.add_argument("--all", action="store_true", help="Include settled historical trades")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--remote", action="store_true", help="Execute against production GCP VM (weather-bot-free)")
    args = parser.parse_args()

    if args.remote:
        remote_cmd = "/opt/weather-bot/venv/bin/python /opt/weather-bot/scripts/prd_position_report.py"
        if args.all:
            remote_cmd += " --all"
        if args.json:
            remote_cmd += " --json"
        cmd = [
            "gcloud", "compute", "ssh",
            "--zone=us-central1-a",
            "weather-bot-free",
            f"--command={remote_cmd}",
        ]
        sys.exit(subprocess.call(cmd))

    asyncio.run(build_and_print_report(args.db, include_settled=args.all, as_json=args.json))


if __name__ == "__main__":
    main()
