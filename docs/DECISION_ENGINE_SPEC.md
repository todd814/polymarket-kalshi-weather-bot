# Weather Trading Bot: Decision Engine & Execution Specification

This guide serves as the definitive reference for how the weather prediction market bot operates, evaluates signals, manages risk, and executes trades on Kalshi. Any LLM, agent, or engineer modifying or auditing this codebase **must** adhere strictly to the rules, pipelines, and mathematical models documented below.

---

## 1. High-Level System Architecture

The bot runs on an automated loop (`backend/core/scheduler.py`) executing every 5 minutes (`WEATHER_SCAN_INTERVAL_SECONDS = 300`):

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Data Ingestion                                           │
│    - Kalshi Markets (KXHIGH* tickers for 10 US cities)      │
│    - 82-Member Ensemble Weather Forecasts (Open-Meteo)     │
│    - Official NWS ASOS Airport Surface Observations        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Signal Generation (backend/core/weather_signals.py)      │
│    - Question Parsing (high/low, above/below/between)       │
│    - Raw Probability Computation from 82 Ensemble Members   │
│    - High-Water Mark Ratchet (NWS ASOS Ground Truth)        │
│    - Tail-Risk Probability Clamping (0.85 max cap)          │
│    - Directional Edge Calculation against Order Book Asks   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Signal Filtering & Guardrails (The Defense Layer)        │
│    - Liquidity Spread Filter (spread <= 10¢)                │
│    - Entry Price Boundaries (6¢ floor, 68¢ ceiling)         │
│    - Phantom Edge Guard (Max 35% divergence vs liquid book) │
│    - Calibration Lockout Gate                               │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Position Sizing (Kelly Criterion)                        │
│    - Binary Option Fractional Kelly (f* = (p - ask)/(1-ask))│
│    - Effective Edge Clamping (capped at 25% for sizing)     │
│    - 15% Fractional Kelly Multiplier                        │
│    - Hard Max Trade Cap ($5.00)                             │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Portfolio Risk & Staging (backend/core/scheduler.py)     │
│    - Staged Exposure Buckets (25% Today, 12.5% Future)      │
│    - Future Hurdle Filter (12% minimum edge for T+1)        │
│    - City-Date Concentration Cap (Max 1 live pos per city)  │
│    - Sub-$1.00 Dust Top-Up Merging Logic                    │
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

### Covered Cities (10 Core US Airport Climatological Stations)
Mapped via `CITY_CONFIG` in `backend/data/weather.py`:
- `nyc`: New York (KNYC Central Park / KLGA / KJFK)
- `chicago`: Chicago O'Hare (KORD)
- `miami`: Miami International (KMIA)
- `los_angeles`: Los Angeles International (KLAX)
- `denver`: Denver International (KDEN)
- `austin`: Austin-Bergstrom (KAUS / KATT)
- `houston`: Houston Intercontinental (KIAH)
- `washington_dc`: Reagan National (KDCA)
- `boston`: Boston Logan (KBOS)
- `philadelphia`: Philadelphia International (KPHL)

### Forecast Ensemble
- **API:** Open-Meteo Ensemble API (`fetch_ensemble_forecast`).
- **Ensemble Blend:** GFS (31 members) + ECMWF IFS (51 members) = 82 total ensemble forecast members.
- **Metric Extraction:** Computes exact member counts above, below, or between temperature thresholds.

### Ground Truth (NWS ASOS Observations)
- Official METAR surface station reports fetched via National Weather Service API (`api.weather.gov`).
- Used to observe the daily high temperature recorded so far today.

---

## 3. Signal Generation & Decision Math

### A. Raw Model Probability
Count fraction of the 82 ensemble members satisfying the contract strike condition:
$$\text{raw\_yes\_prob} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{member}_i \text{ satisfies condition})}{N}$$

### B. High-Water Mark Ratchet (Ground Truth Guarantee)
For same-day contracts (`target_date == today`), temperature is monotonically non-decreasing during daylight hours. If current observed high from the official NWS ASOS station already resolves the strike:
- **Above / Greater:** If $\text{observed\_high} \ge \text{threshold} + 0.5^\circ\text{F} \implies P(\text{YES}) = 0.999$ (Guaranteed Win).
- **Below / Less:** If $\text{observed\_high} \ge \text{threshold} - 0.5^\circ\text{F} \implies P(\text{YES}) = 0.001$ (Guaranteed Loss / 0.999 NO).
- **Between Bracket:** If $\text{observed\_high} \ge \text{cap} + 0.5^\circ\text{F} \implies P(\text{YES}) = 0.001$ (Exceeded Upper Bound / 0.999 NO).

### C. Tail-Risk Probability Clamping
Unless an ASOS ratchet is active, numerical weather prediction models have coarse resolution (9km–25km grids) and cannot model hyper-local microclimates with 100% certainty.
- If no ratchet is applied, win probability is clamped at **0.85 maximum**:
  $$P(\text{YES}) = \min(0.85, \text{raw\_yes\_prob})$$
  $$P(\text{NO}) = \min(0.85, 1.0 - \text{raw\_yes\_prob})$$
- Prevents extreme overconfidence on 0/82 or 82/82 member consensus.

### D. Directional Edge Calculation
Always computed against the actual ask price required to enter the position:
$$\text{yes\_edge} = P(\text{YES}) - \text{market\_yes\_ask}$$
$$\text{no\_edge} = P(\text{NO}) - \text{market\_no\_ask}$$
The bot selects the direction with higher positive edge ($\text{yes}$ or $\text{no}$).

---

## 4. Signal Filtering & Protective Guardrails

Before any trade can be considered, it must clear five consecutive filters:

1. **Spread Gate:**
   $$\text{Spread} = (\text{yes\_ask} + \text{no\_ask}) - 1.00 \le 0.10 \text{ (10¢ max)}$$
   *Note:* In an empty book where one side has no resting bid, Kalshi quotes 1.0000. This is treated as a one-sided quote rather than an invalid spread.
2. **Entry Price Floor:**
   - Single Threshold contracts (`-T`): $\text{entry\_price} \ge 0.06$ (6¢).
   - Bracket contracts (`-B` YES): $\text{entry\_price} \ge 0.12$ (12¢).
   *(Eliminates negative-EV longshot lottery tickets).*
3. **Entry Price Ceiling:**
   $$\text{entry\_price} \le 0.68 \text{ (68¢ max)}$$
   *(Historical audit demonstrated trades bought above 68¢ had negative expectancy due to poor risk/reward asymmetry).*
4. **Phantom Edge Guard (`WEATHER_MAX_DIVERGENCE = 0.35`):**
   $$|P_{\text{model}}(\text{YES}) - P_{\text{market}}(\text{YES})| \le 0.35$$
   If the model disagrees with a liquid book by $>35\%$ (and no ASOS ratchet is active), it indicates **model basis risk** (the global model missing local mesoscale physics like sea breezes or inversion layers) rather than free alpha. The trade is rejected.
5. **Minimum Edge Hurdle:**
   - Same-Day (Today / T+0): $\text{Edge} \ge 0.08$ (8% minimum edge).
   - Future (Tomorrow / T+1): $\text{Edge} \ge 0.12$ (12% stricter hurdle).

---

## 5. Position Sizing (Fractional Kelly)

The bot sizes positions using the binary option Kelly criterion:
$$f^* = \frac{P_{\text{win}} - \text{ask}}{1 - \text{ask}}$$
Adjustments applied:
- **Edge Clamping for Sizing:** Effective edge is clamped at $0.25$ ($25\%$) when calculating Kelly size to prevent sizing blowouts on overconfident tails.
- **Fractional Kelly Multiplier:** $f_{\text{actual}} = f^* \times 0.15$ (`KELLY_FRACTION = 0.15`).
- **Maximum Per-Trade Allocation:** Capped at $5\%$ of total bankroll.
- **Hard Trade Size Cap:** $\min(\text{size}, \$5.00)$ (`WEATHER_MAX_TRADE_SIZE = 5.0`).
- **Minimum Order Floor:** $\$1.00$ (`MIN_TRADE_SIZE = 1.0`).

---

## 6. Portfolio Allocation & Capital Preservation

The bot segregates capital into two rolling temporal buckets to avoid over-allocating to distant forecasts while preserving dry powder for same-day precision:

| Bucket | Allocation Cap | Min Floor | Edge Hurdle | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Today (T+0)** | $25\%$ of Bankroll | $\$25.00$ | $8\%$ | Same-day high-precision execution + ASOS ratchet locks |
| **Future (T+1)** | $12.5\%$ of Bankroll | $\$12.50$ | $12\%$ | Capturing high-conviction early market mispricings for tomorrow |

- **Maturation:** At 00:00 EST, Future (T+1) positions mature into Today (T+0), freeing up the Future bucket for the next day's forecast.
- **Outcome-Pending Bypass:** Positions where an ASOS ratchet has locked a win or outcome is pending settlement are excluded from consuming the open risk cap.
- **City-Date Concentration Cap:**
  `WEATHER_MAX_POSITIONS_PER_CITY_DATE = 1`
  The bot is strictly prohibited from holding more than 1 active live contract per city per target date. This prevents cluster failures where multiple strikes in the same city collapse from one synoptic weather shift.
- **Sub-$1.00 Dust Fill Consolidation:**
  If an IOC order receives a partial fractional fill (e.g., $\$0.03$ or $\$0.05$ fill due to thin liquidity), subsequent scans identify the existing position as a "dust stub," allow topping it up to the $\$1.00$ minimum, and merge the database trade record.

---

## 7. Order Execution & Settlement

- **Order Type:** Immediate-or-Cancel (IOC) limit order via Kalshi REST API (`KalshiClient.create_order`).
- **Unfilled Handling:** If filled contracts equal 0, the trade is rejected and not recorded.
- **Settlement Engine:** Runs every 30 minutes (`backend/core/settlement.py`), fetching official Kalshi market resolutions and NWS daily summary observations, reconciling realized P&L, and updating the database state.

---

## 8. Rules for Future LLMs & Developers

1. **DO NOT Over-Engineer:** Do not add complex neural nets, multi-agent debates, or extraneous indicators to the decision loop. The bot's edge comes from disciplined probability calibration, tight risk controls, and NWS ground truth.
2. **Preserve Protective Filters:** Never disable the **Phantom Edge Guard (35%)**, the **Entry Price Floor (6¢/12¢)**, or the **City-Date Concentration Cap (1 per city/date)**.
3. **Maintain Unit Test Coverage:** Any change to signal generation or execution must pass all unit tests in `test_c137_quant.py`. Run:
   ```bash
   ./venv/bin/python -m unittest test_c137_quant.py
   ```
4. **Production Deployment:** Changes to `backend/` must be deployed and restarted on the GCP VM (`weather-bot-free`, service: `weather-bot.service`). Verify with:
   ```bash
   sudo systemctl restart weather-bot.service
   sudo journalctl -u weather-bot.service -n 50 --no-pager
   ```
