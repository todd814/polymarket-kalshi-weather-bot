# Weather Trading Bot: Decision Engine & Execution Specification

This guide serves as the definitive reference for how the weather prediction market bot operates, evaluates signals, manages risk, and executes trades on Kalshi. Any LLM, agent, or engineer modifying or auditing this codebase **must** adhere strictly to the rules, pipelines, and mathematical models documented below.

---

## 1. High-Level System Architecture

The bot runs on an automated loop (`backend/core/scheduler.py`) executing every 5 minutes (`WEATHER_SCAN_INTERVAL_SECONDS = 300`):

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Data Ingestion                                           │
│    - Kalshi Markets (10 verified KXHIGH/KXHIGHT series)      │
│    - 82-Member Ensemble + NBM (2.5km) & NWS Gridpoint Anchor│
│    - DST-Aware NWS ASOS Observations + 6h Intra-Hour Max    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Signal Generation (backend/core/weather_signals.py)      │
│    - Question Parsing (high/low, above/below/between)       │
│    - Bias Recentering & Spread Inflation (min 1.3F/2.0F)    │
│    - Station-Local High-Water Mark Ratchet (ASOS Truth)     │
│    - 30% Bayesian Market Shrinkage + 0.85 Confidence Cap    │
│    - Fee-Adjusted Directional Edge vs Order Book Asks       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Signal Filtering & Guardrails (The Defense Layer)        │
│    - Liquidity Spread Filter (spread <= 10¢)                │
│    - Entry Price Boundaries (20¢ floor, 68¢ ceiling)        │
│    - Unclipped Phantom Edge Guard (Max 35% vs ref market)   │
│    - Rolling 30-Trade Calibration Lockout Gate              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Position Sizing (Fee-Adjusted Kelly Criterion)           │
│    - Binary Kelly f* = min(edge, p - eff_ask) / (1-eff_ask) │
│    - Effective Edge Clamping (actually enforced 25% cap)    │
│    - 15% Fractional Kelly Multiplier                        │
│    - Hard Max Trade Cap ($5.00)                             │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Portfolio Risk & Staging (backend/core/scheduler.py)     │
│    - Proportional Buckets (25% Today, 12.5% Future)         │
│    - T+1 Timing Gate (>= 18:00 UTC) + 12% Edge Hurdle       │
│    - Live Non-Ratchet Threshold (-T) Quarantine             │
│    - City-Date Concentration Cap (Max 1 live pos per city)  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Execution & Persistence                                  │
│    - Kalshi REST API IOC (Immediate-or-Cancel) Order        │
│    - Database Record Creation / Top-Up Update (tradingbot.db)│
│    - Settlement Engine (backend/core/settlement.py)         │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Ingestion & Data Sources

### Covered Cities (10 Verified Kalshi Official CLI Stations)
Mapped via `CITY_CONFIG` in `backend/data/weather.py`:
- `nyc`: New York Central Park (`KNYC`) — Series `KXHIGHNY`
- `chicago`: Chicago Midway (`KMDW` / `CLIMDW`) — Series `KXHIGHCHI`
- `miami`: Miami International (`KMIA`) — Series `KXHIGHMIA`
- `los_angeles`: Los Angeles International (`KLAX`) — Series `KXHIGHLAX`
- `denver`: Denver International (`KDEN`) — Series `KXHIGHDEN`
- `austin`: Austin-Bergstrom (`KAUS` / `CLIAUS`) — Series `KXHIGHAUS`
- `houston`: Houston Hobby (`KHOU` / `CLIHOU`) — Series `KXHIGHTHOU`
- `washington_dc`: Reagan National (`KDCA`) — Series `KXHIGHTDC`
- `boston`: Boston Logan (`KBOS`) — Series `KXHIGHTBOS`
- `philadelphia`: Philadelphia International (`KPHL`) — Series `KXHIGHPHIL`

### Forecast Ensemble & Bias Anchors
- **Ensemble Blend:** Open-Meteo GFS (31 members) + ECMWF IFS (51 members) = 82 members.
- **High-Res Bias Anchors:** `ncep_nbm_conus` (2.5 km MOS-bias-corrected) + official NWS Gridpoint Forecast (`api.weather.gov/gridpoints`). Recentered via `0.55*NBM + 0.45*NWS` with `1.35x` spread inflation (`1.3°F` T+0 / `2.0°F` T+1 floor).

### Ground Truth (NWS ASOS Observations)
- Official METAR surface station reports fetched via National Weather Service API (`api.weather.gov`), using DST-aware station `ZoneInfo` local midnight and `maxTemperatureLast6Hours` (post-06:00 local).

---

## 3. Signal Generation & Decision Math

### A. Raw Model Probability
Count fraction of the 82 ensemble members satisfying the contract strike condition:
$$\text{raw\_yes\_prob} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{member}_i \text{ satisfies condition})}{N}$$

### B. Station-Local High-Water Mark Ratchet (Ground Truth Guarantee)
For same-day contracts (`target_date == station_local_today`), temperature is monotonically non-decreasing during daylight hours. If current observed high from the official NWS ASOS station already resolves the strike:
- **Above / Greater:** If $\text{observed\_high} \ge \text{threshold} + 0.5^\circ\text{F} \implies P(\text{YES}) = 0.999$ (Guaranteed Win).
- **Below / Less:** If $\text{observed\_high} \ge \text{threshold} - 0.5^\circ\text{F} \implies P(\text{YES}) = 0.001$ (Guaranteed Loss / 0.999 NO).
- **Between Bracket:** If $\text{observed\_high} \ge \text{cap} + 0.5^\circ\text{F} \implies P(\text{YES}) = 0.001$ (Exceeded Upper Bound / 0.999 NO).

### C. Bayesian Market Shrinkage & Tail-Risk Clamping
Unless an ASOS ratchet is active, the raw ensemble probability is shrunk 30% toward the clean market reference prior (`market_ref_yes`) and capped at **0.85 maximum**:
$$P_{\text{shrunk}}(\text{YES}) = 0.70 \cdot \text{raw\_yes\_prob} + 0.30 \cdot \text{market\_ref\_yes}$$
$$P(\text{YES}) = \min(0.85, P_{\text{shrunk}}(\text{YES})), \quad P(\text{NO}) = \min(0.85, 1.0 - P_{\text{shrunk}}(\text{YES}))$$

### D. Fee-Adjusted Directional Edge Calculation
Computed net of Kalshi's exact taker fee ($0.07 \cdot P \cdot (1 - P)$ per contract):
$$\text{yes\_edge} = P(\text{YES}) - \text{market\_yes\_ask} - \text{fee}(\text{market\_yes\_ask})$$
$$\text{no\_edge} = P(\text{NO}) - \text{market\_no\_ask} - \text{fee}(\text{market\_no\_ask})$$
The bot selects the direction with higher positive net edge ($\text{yes}$ or $\text{no}$).

---

## 4. Signal Filtering & Protective Guardrails

Before any trade can be considered, it must clear five consecutive filters:

1. **Spread Gate:**
   $$\text{Spread} = (\text{yes\_ask} + \text{no\_ask}) - 1.00 \le 0.10 \text{ (10¢ max)}$$
   *Note:* In an empty book where one side has no resting bid, Kalshi quotes 1.0000. This is treated as a one-sided quote rather than an invalid spread.
2. **Entry Price Floor (`0.20`):**
   - Minimum entry price for all live contracts (`-T` and `-B` YES/NO): $\text{entry\_price} \ge 0.20$ (20¢).
   *(Historical audit: sub-20¢ live trades went 0W/13L).*
3. **Entry Price Ceiling (`0.68`):**
   $$\text{entry\_price} \le 0.68 \text{ (68¢ max)}$$
4. **Unclipped Phantom Edge Guard (`WEATHER_MAX_DIVERGENCE = 0.35`):**
   $$|\text{raw\_yes\_prob} - \text{market\_ref\_yes}| \le 0.35$$
   Measured on unclipped `raw_yes_prob` against clean `market_ref_yes` (including one-sided empty books).
5. **Minimum Edge Hurdle:**
   - Same-Day (Today / T+0): $\text{Edge} \ge 0.08$ (8% net edge).
   - Future (Tomorrow / T+1): $\text{Edge} \ge 0.12$ (12% net edge), gated until `18:00 UTC`.

---

## 5. Position Sizing (Fee-Adjusted Fractional Kelly)

The bot sizes positions using the fee-adjusted binary Kelly criterion with effective cost $P_{\text{eff}} = \text{ask} + \text{fee}$:
$$f^* = \frac{\min(\text{edge\_cap}, P_{\text{win}} - P_{\text{eff}})}{1 - P_{\text{eff}}}$$
Adjustments applied:
- **Edge Clamping for Sizing:** Effective edge is actively capped at $0.25$ ($25\%$) inside `calculate_kelly_size`.
- **Fractional Kelly Multiplier:** $f_{\text{actual}} = f^* \times 0.15$ (`KELLY_FRACTION = 0.15`).
- **Maximum Per-Trade Allocation:** Capped at $5\%$ of total bankroll or $\$5.00$ (`WEATHER_MAX_TRADE_SIZE = 5.0`).
- **Minimum Order Floor:** $\$1.00$ (`MIN_TRADE_SIZE = 1.0`).

---

## 6. Portfolio Allocation & Capital Preservation

The bot segregates capital into two strictly proportional temporal buckets:

| Bucket | Proportional Cap | Timing / Type Gate | Edge Hurdle | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Today (T+0)** | $25\%$ of Bankroll | 24/7 (Non-ratchet `-T` paused live) | $8\%$ | Same-day high-precision execution + ASOS ratchet locks |
| **Future (T+1)** | $12.5\%$ of Bankroll | After `18:00 UTC` only | $12\%$ | Pre-allocation after 12Z NBM/ECMWF/GFS + deeper books |

- **Rolling Self-Healing Calibration:** Kill-switch audits a rolling `30`-trade window (`WEATHER_CALIBRATION_ROLLING_WINDOW = 30`). ASOS ratchets are exempt from lockout.
- **City-Date Concentration Cap:** `WEATHER_MAX_POSITIONS_PER_CITY_DATE = 1`.
- **Sub-$1.00 Dust Fill Consolidation:** Sub-$1.00 partial fills are topped up and merged into the existing DB row.

---

## 7. Order Execution & Settlement

- **Order Type:** Immediate-or-Cancel (IOC) limit order via Kalshi REST API (`KalshiClient.create_order`).
- **Unfilled Handling:** If filled contracts equal 0, the trade is rejected and not recorded.
- **Settlement Engine:** Runs every 2 minutes (`settlement_job`), computing exact Kalshi taker fees (`ceil(0.07 * C * P * (1-P))`) and settling strictly on Kalshi official resolution (or DST-aware NWS fallback for Polymarket).

---

## 8. Rules for Future LLMs & Developers

1. **DO NOT Over-Engineer:** Keep the signal pipeline clean, calibrated, and deterministic.
2. **Preserve Protective Filters:** Never disable the **Unclipped Phantom Edge Guard (35%)**, **Entry Price Floor (20¢)**, **Proportional Caps (25%/12.5%)**, or **City-Date Concentration Cap (1 per city/date)**.
3. **Maintain Unit Test Coverage:** Any change to signal generation or execution must pass all unit tests in `test_c137_quant.py`. Run:
   ```bash
   ./venv/bin/python -m unittest test_c137_quant.py
   ```
4. **Production Deployment:** Changes to `backend/` must be deployed and restarted on the GCP VM (`weather-bot-free`, service: `weather-bot.service`). Verify with:
   ```bash
   sudo systemctl restart weather-bot.service
   sudo journalctl -u weather-bot.service -n 50 --no-pager
   ```
