# Graph Report - polymarket-kalshi-weather-bot  (2026-11-06)

## Corpus Check
- 71 files · ~74,807 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 3, .example 2, .jsonl 2)

## Summary
- 866 nodes · 1718 edges · 79 communities (40 shown, 39 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 87 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b6ebf191`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- KalshiClient
- btc_markets.py
- analytics/__init__.py
- package.json
- hourly_signals.py
- scheduler.py
- BotState
- get_dashboard
- init_db
- Trade
- App.tsx
- AILog
- dependencies
- api.ts
- compilerOptions
- WeatherSignal
- ClaudeAnalyzer
- GroqClassifier
- FilterBar.tsx
- EnsembleForecast
- get
- Prediction Market Trading Bot
- base.py
- utils.ts
- ConnectionManager
- EquityChart.tsx
- BaseAIClient
- compilerOptions
- deploy
- AIAnalysis
- claude.py
- WeatherMarket
- _signal_to_response
- SettlementCalibrationHarness
- MicrostructurePanel.tsx
- vercel.json
- frontend/vercel.json
- MicrostructureEngine
- weather_signals.py
- vite-env.d.ts
- Platform and API Research
- Layer 2B: Econ Pipeline
- api/main.py
- test_kalshi_demo.py
- 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)
- Backend Dependencies
- main.tsx
- logging
- SignalsTable.tsx
- test_c137_quant.py
- EdgeDistribution.tsx
- TestC137QuantitativeCore
- stop_scheduler
- TradesTable.tsx
- deploy_gcp.sh
- config.py
- devDependencies
- .test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book
- hourly_scheduler.py
- kalshi_client.py
- scripts
- _compute_calibration_summary
- Base
- get_weather_signals
- vite.config.ts
- get_btc_windows
- get_weather_markets
- run_manual_settlement

## God Nodes (most connected - your core abstractions)
1. `KalshiClient` - 31 edges
2. `Trade` - 30 edges
3. `TestC137QuantitativeCore` - 30 edges
4. `BotState` - 27 edges
5. `App()` - 23 edges
6. `get_dashboard()` - 21 edges
7. `Signal` - 20 edges
8. `EnsembleForecast` - 19 edges
9. `WeatherMarket` - 19 edges
10. `log_event()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Frontend Web Entry Point` --semantically_similar_to--> `Trading Dashboard UI Screenshot`  [INFERRED] [semantically similar]
  frontend/index.html → docs/dashboard.png
- `TestC137QuantitativeCore` --uses--> `SettlementCalibrationHarness`  [INFERRED]
  test_c137_quant.py → backend/analytics/calibration.py
- `TestC137QuantitativeCore` --uses--> `MicrostructureEngine`  [INFERRED]
  test_c137_quant.py → backend/analytics/microstructure.py
- `TestC137QuantitativeCore` --uses--> `WeatherTradingSignal`  [INFERRED]
  test_c137_quant.py → backend/core/weather_signals.py
- `TestC137QuantitativeCore` --uses--> `KalshiClient`  [INFERRED]
  test_c137_quant.py → backend/data/kalshi_client.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Weather Trading Subsystem** — architecture_layer2a_weather_pipeline, readme_strategy_weather_temperature, validated_research_kalshi_weather_tickers [INFERRED 0.85]

## Communities (79 total, 39 thin omitted)

### Community 1 - "btc_markets.py"
Cohesion: 0.06
Nodes (21): BtcMarket, _compute_window_slugs(), fetch_active_btc_markets(), fetch_btc_market_by_slug(), fetch_btc_market_for_settlement(), is_valid_btc_slug(), _parse_event_to_btc_market(), _round_to_5min() (+13 more)

### Community 2 - "analytics/__init__.py"
Cohesion: 0.23
Nodes (3): ArbitrageOpportunity, MonotonicityScanner, GateResult

### Community 3 - "package.json"
Cohesion: 0.10
Nodes (19): name, private, type, version, autoprefixer, clsx, d3-geo, leaflet (+11 more)

### Community 4 - "hourly_signals.py"
Cohesion: 0.07
Nodes (19): compute_coastal_drift_and_sigma(), _estimate_diurnal_drift_per_hour(), evaluate_hourly_market(), HourlySignal, _normal_cdf(), scan_for_hourly_signals(), compute_seasonal_diurnal_drift(), compute_solar_ephemeris() (+11 more)

### Community 5 - "scheduler.py"
Cohesion: 0.09
Nodes (7): calculate_edge(), generate_btc_signal(), get_actionable_signals(), _persist_signals(), scan_for_signals(), test(), TradingSignal

### Community 6 - "BotState"
Cohesion: 0.16
Nodes (15): reset_bot(), run_scan(), settle_trades_endpoint(), simulate_trade(), start_bot(), startup(), stop_bot(), heartbeat_job() (+7 more)

### Community 7 - "get_dashboard"
Cohesion: 0.18
Nodes (11): BotStats, BtcPriceResponse, DashboardData, get_btc_price(), get_dashboard(), get_stats(), get_trades(), get_weather_forecasts() (+3 more)

### Community 9 - "Trade"
Cohesion: 0.14
Nodes (12): settlement_job(), calculate_pnl(), check_market_settlement(), check_weather_settlement(), _fetch_kalshi_resolution(), _fetch_nws_resolution(), fetch_polymarket_resolution(), _parse_market_resolution() (+4 more)

### Community 10 - "App.tsx"
Cohesion: 0.22
Nodes (17): fetchDashboard(), fetchHourlySignals(), fetchMetar(), runScan(), simulateTrade(), startBot(), stopBot(), App() (+9 more)

### Community 11 - "AILog"
Cohesion: 0.14
Nodes (3): AICallLogger, AICallRecord, AILog

### Community 12 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, axios, clsx, d3-geo, date-fns, framer-motion, leaflet, lucide-react (+11 more)

### Community 13 - "api.ts"
Cohesion: 0.13
Nodes (9): api, Props, BtcPrice, BtcWindow, CalibrationSummary, DashboardData, MetarObservation, Signal (+1 more)

### Community 14 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+10 more)

### Community 15 - "WeatherSignal"
Cohesion: 0.36
Nodes (7): CITIES, CityMarker, Props, Props, WeatherForecast, WeatherSignal, react-globe.gl

### Community 18 - "FilterBar.tsx"
Cohesion: 0.40
Nodes (3): FilterState, Props, STATUSES

### Community 20 - "get"
Cohesion: 0.14
Nodes (8): get_c137_calibration(), get_equity_curve(), get_hourly_signals(), get_kalshi_status(), get_metar_observations(), health(), root(), serve_frontend()

### Community 21 - "Prediction Market Trading Bot"
Cohesion: 0.17
Nodes (11): Layer 1: Market Scanner, Layer 2A: Weather Pipeline, Trading Bot Architecture, Trading Dashboard UI Screenshot, Frontend Web Entry Point, Fractional Kelly Criterion Sizing, Prediction Market Trading Bot, BTC 5-Minute Microstructure Strategy (+3 more)

### Community 23 - "utils.ts"
Cohesion: 0.22
Nodes (3): AgreementBar(), WeatherPanel(), platformStyles

### Community 25 - "EquityChart.tsx"
Cohesion: 0.27
Nodes (8): CustomTooltip(), EquityChart(), Props, Props, BotStats, EquityPoint, framer-motion, recharts

### Community 27 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, include

### Community 28 - "deploy"
Cohesion: 0.25
Nodes (7): build, builder, deploy, healthcheckPath, restartPolicyType, startCommand, $schema

### Community 31 - "WeatherMarket"
Cohesion: 0.17
Nodes (5): WeatherTradingSignal, WeatherMarket, run_dual_track_verification(), run_test(), run_scheduler_and_settlement_checks()

### Community 32 - "_signal_to_response"
Cohesion: 0.33
Nodes (4): get_actionable_signals(), get_signals(), _signal_to_response(), SignalResponse

### Community 34 - "MicrostructurePanel.tsx"
Cohesion: 0.53
Nodes (5): MeterBar(), MicrostructurePanel(), Props, RsiGauge(), Microstructure

### Community 35 - "vercel.json"
Cohesion: 0.33
Nodes (5): builds, name, routes, $schema, version

### Community 36 - "frontend/vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, framework, outputDirectory, rewrites

### Community 38 - "weather_signals.py"
Cohesion: 0.15
Nodes (8): calculate_kelly_size(), generate_weather_signal(), _persist_weather_signals(), scan_for_weather_signals(), _celsius_to_fahrenheit(), fetch_ensemble_forecast(), fetch_nws_observed_temperature(), test_weather_ensemble_and_edge_calculation()

### Community 44 - "api/main.py"
Cohesion: 0.19
Nodes (4): EventResponse, get_events(), websocket_events(), get_recent_events()

### Community 46 - "test_kalshi_demo.py"
Cohesion: 0.24
Nodes (8): _extract_price(), fetch_kalshi_weather_markets(), _parse_kalshi_market(), main(), test_kalshi_demo_connectivity(), test_kalshi_demo_weather_market_scan(), test_rsa_pss_auth_layer(), test_ticker_and_price_parsing()

### Community 48 - "🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)"
Cohesion: 0.13
Nodes (14): 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever), ⚡ 24/7 Operations & Maintenance, Accessing the Web Dashboard, Check Service Status, Deploy to Cloud Run:, 💰 How is it $0 / Month Forever?, 🚀 Option A: 1-Click Automated Deployment (`deploy_gcp.sh`), 🛠️ Option B: Manual Setup on Any GCP VM (+6 more)

### Community 52 - "main.tsx"
Cohesion: 0.18
Nodes (7): ErrorBoundary, Props, State, queryClient, react, react-dom, @tanstack/react-query

### Community 53 - "logging"
Cohesion: 0.18
Nodes (4): _extract_date(), fetch_polymarket_weather_markets(), _parse_polymarket_weather(), _parse_weather_market_title()

### Community 54 - "SignalsTable.tsx"
Cohesion: 0.36
Nodes (7): CategoryBadge(), EdgeBar(), PlatformBadge(), SignalsTable(), SortDir, SortKey, UnifiedSignal

### Community 56 - "EdgeDistribution.tsx"
Cohesion: 0.36
Nodes (7): BUCKETS, CustomTooltip(), EdgeDistribution(), getBucket(), Props, Props, HourlySignal

### Community 59 - "TradesTable.tsx"
Cohesion: 0.22
Nodes (8): LogEntry, Props, Props, SortDir, SortKey, Trade, date-fns, lucide-react

### Community 63 - "devDependencies"
Cohesion: 0.22
Nodes (9): devDependencies, autoprefixer, postcss, tailwindcss, @types/react, @types/react-dom, typescript, vite (+1 more)

### Community 65 - "hourly_scheduler.py"
Cohesion: 0.21
Nodes (5): get_city_for_ticker(), hourly_scan_and_trade_job(), hourly_settlement_job(), parse_expiry_from_ticker(), Signal

### Community 67 - "scripts"
Cohesion: 0.50
Nodes (4): scripts, build, dev, preview

### Community 68 - "_compute_calibration_summary"
Cohesion: 0.33
Nodes (4): CalibrationBucket, CalibrationSummary, _compute_calibration_summary(), get_calibration()

### Community 70 - "get_weather_signals"
Cohesion: 0.50
Nodes (3): get_weather_signals(), _weather_signal_to_response(), WeatherSignalResponse

## Knowledge Gaps
- **122 isolated node(s):** `Config`, `deploy_gcp.sh script`, `name`, `private`, `version` (+117 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 431 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **39 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestC137QuantitativeCore` connect `TestC137QuantitativeCore` to `KalshiClient`, `SettlementCalibrationHarness`, `.test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book`, `MicrostructureEngine`, `BotState`, `.test_nws_local_midnight_and_obs_cache`, `Trade`, `.test_nws_observation_weather_settlement_fallback`, `.test_weather_signal_ratchet_and_single_db_session`, `.test_kalshi_v2_create_order_yes_leg_and_auth_hygiene`, `EnsembleForecast`, `test_c137_quant.py`, `WeatherMarket`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `KalshiClient` (e.g. with `get_kalshi_status()` and `reset_bot()`) actually correct?**
  _`KalshiClient` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Config`, `deploy_gcp.sh script`, `name` to the rest of the system?**
  _122 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `KalshiClient` be split into smaller, more focused modules?**
  _Cohesion score 0.12681159420289856 - nodes in this community are weakly interconnected._
- **Why does `KalshiClient` connect `KalshiClient` to `kalshi_client.py`, `hourly_signals.py`, `scheduler.py`, `BotState`, `Trade`, `api/main.py`, `.test_kalshi_v2_create_order_yes_leg_and_auth_hygiene`, `test_kalshi_demo.py`, `get`, `logging`, `test_c137_quant.py`, `TestC137QuantitativeCore`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Trade` (e.g. with `get_dashboard()` and `get_equity_curve()`) actually correct?**
  _`Trade` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Should `btc_markets.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05639097744360902 - nodes in this community are weakly interconnected._