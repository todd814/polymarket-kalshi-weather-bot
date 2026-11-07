"""
=============================================================================
C-137 QUANTITATIVE UNIT TEST MATRIX
Tests:
  1. Becker Favorite-Longshot Bias (FLB) warping
  2. Order Book Imbalance (OBI) computation
  3. Friction & Net Edge hurdle calculation
  4. Frigo Brier Score & Negative-Edge Lockdown Kill Switch
  5. Octagon 5-Gate Fortress Risk Governor
=============================================================================
"""

import unittest
from backend.analytics.microstructure import MicrostructureEngine
from backend.analytics.calibration import SettlementCalibrationHarness
from backend.analytics.risk_governor import OmniRiskGovernor


class TestC137QuantitativeCore(unittest.TestCase):

    def setUp(self):
        self.micro = MicrostructureEngine(flb_alpha=0.88, taker_fee_pct=0.015)
        # Use an isolated in-memory test harness
        self.calib = SettlementCalibrationHarness(
            journal_path="/tmp/test_c137_journal.jsonl",
            brier_threshold=0.245,
            min_trades_for_audit=3
        )
        self.risk = OmniRiskGovernor(
            max_spread=0.08,
            min_net_edge=0.03,
            max_drawdown_pct=0.15,
            max_category_exposure_pct=0.35,
            kelly_fraction=0.25
        )

    def test_becker_flb_warping(self):
        """Longshots (p < 0.5) must be depressed, favorites (p > 0.5) rewarded."""
        p_longshot = 0.10
        calibrated_longshot = self.micro.calibrate_probability(p_longshot)
        self.assertLess(calibrated_longshot, p_longshot, "Longshot probability must be discounted")

        p_favorite = 0.90
        calibrated_favorite = self.micro.calibrate_probability(p_favorite)
        self.assertGreater(calibrated_favorite, p_favorite, "Favorite probability must be increased")

    def test_order_book_imbalance(self):
        """OBI must reflect buy vs sell pressure in range [-1.0, 1.0]."""
        heavy_bids = [(0.50, 100.0), (0.49, 100.0)]
        light_asks = [(0.52, 10.0), (0.53, 10.0)]
        obi_buy = self.micro.compute_order_book_imbalance(heavy_bids, light_asks)
        self.assertGreater(obi_buy, 0.5, "Strong bid depth must produce positive OBI")

        obi_sell = self.micro.compute_order_book_imbalance(light_asks, heavy_bids)
        self.assertLess(obi_sell, -0.5, "Heavy ask volume must produce negative OBI")

    def test_net_edge_friction_hurdle(self):
        """Gross edge must be penalized by taker fee and slippage."""
        # Raw edge is 2.5%, but min hurdle is 3% -> should reject
        has_edge, net_edge, _ = self.micro.extract_net_edge(
            model_prob=0.525,
            market_price=0.50,
            contracts=10.0,
            min_hurdle=0.03
        )
        self.assertFalse(has_edge, "Edge below net hurdle must be rejected")

        # Large edge 15% should easily pass
        has_edge_large, net_edge_large, _ = self.micro.extract_net_edge(
            model_prob=0.70,
            market_price=0.50,
            contracts=10.0,
            min_hurdle=0.03
        )
        self.assertTrue(has_edge_large, "Sufficient edge after friction must pass")

    def test_frigo_brier_kill_switch(self):
        """When Brier score degrades past 0.245, category must be locked down."""
        # 3 consecutive bad predictions (model says 90%, outcome is 0.0)
        for i in range(3):
            self.calib.record_settlement(
                trade_id=f"test_{i}",
                ticker="TEST_TICKER",
                category="test_cat",
                predicted_prob=0.90,
                actual_outcome=0.0,
                size=10.0,
                entry_price=0.50,
                pnl=-10.0
            )

        brier = self.calib.get_category_brier("test_cat")
        self.assertGreater(brier, 0.245, "Brier score must be high on consecutive misses")

        is_permitted, reason = self.calib.is_category_permitted("test_cat")
        self.assertFalse(is_permitted, "Category must be locked out after 3 bad misses")
        self.assertIn("NEGATIVE EDGE LOCKDOWN", reason)

    def test_octagon_5_gate_fortress(self):
        """Order must pass all gates or be rejected with exact gate number."""
        # Gate 1 test: Wide spread (12c > 8c limit)
        g1_res = self.risk.evaluate_order(
            category="weather",
            entry_price=0.50,
            model_prob=0.70,
            net_edge=0.15,
            spread=0.12,  # > 0.08
            current_bankroll=100.0,
            category_exposure=0.0,
            high_water_mark=100.0
        )
        self.assertFalse(g1_res.passed)
        self.assertEqual(g1_res.gate_failed, 1)

        # Gate 5 test: Max drawdown exceeded (20% > 15% limit)
        g5_res = self.risk.evaluate_order(
            category="weather",
            entry_price=0.50,
            model_prob=0.70,
            net_edge=0.15,
            spread=0.04,
            current_bankroll=80.0,  # 20% drawdown from 100
            category_exposure=0.0,
            high_water_mark=100.0
        )
        self.assertFalse(g5_res.passed)
        self.assertEqual(g5_res.gate_failed, 5)

        # Valid order passing all gates
        good_res = self.risk.evaluate_order(
            category="weather",
            entry_price=0.50,
            model_prob=0.70,
            net_edge=0.15,
            spread=0.04,
            current_bankroll=100.0,
            category_exposure=10.0,
            high_water_mark=100.0
        )
        self.assertTrue(good_res.passed)
        self.assertGreater(good_res.approved_size, 0.0)

    def test_nws_continuity_correction_and_partition_identity(self):
        """
        Verify +/-0.5F NWS integer rounding continuity correction:
          - below(70) covers (-inf, 69.5)
          - between(70, 71) covers [69.5, 71.5) (full 2.0F bracket width)
          - above(71) covers [71.5, +inf)
          - Exact probability partition: P(below 70) + P(between 70, 71) + P(above 71) == 1.0
        """
        from datetime import date
        from backend.data.weather import EnsembleForecast

        # Include boundary values: 69.49 (below 70), 69.50 (in 70-71), 70.0, 70.8, 71.49 (in 70-71), 71.50 (above 71)
        members = [68.0, 69.49, 69.50, 70.0, 70.5, 71.0, 71.49, 71.50, 72.0, 75.0]
        fc = EnsembleForecast(
            city_key="nyc",
            city_name="New York City",
            target_date=date(2026, 10, 28),
            member_highs=members,
            member_lows=members,
        )

        p_below_70 = fc.probability_high_below(70.0)          # 68.0, 69.49 -> 2/10 = 0.2
        p_between_70_71 = fc.probability_high_between(70.0, 71.0)  # 69.50, 70.0, 70.5, 71.0, 71.49 -> 5/10 = 0.5
        p_above_71 = fc.probability_high_above(71.0)          # 71.50, 72.0, 75.0 -> 3/10 = 0.3

        self.assertAlmostEqual(p_below_70, 0.2)
        self.assertAlmostEqual(p_between_70_71, 0.5)
        self.assertAlmostEqual(p_above_71, 0.3)
        self.assertAlmostEqual(p_below_70 + p_between_70_71 + p_above_71, 1.0)

        # Low temperature continuity correction & partition identity
        self.assertAlmostEqual(fc.probability_low_below(70.0), 0.2)
        self.assertAlmostEqual(fc.probability_low_between(70.0, 71.0), 0.5)
        self.assertAlmostEqual(fc.probability_low_above(71.0), 0.3)
        self.assertAlmostEqual(
            fc.probability_low_below(70.0) + fc.probability_low_between(70.0, 71.0) + fc.probability_low_above(71.0),
            1.0,
        )

        # Empty ensemble fallback priors
        empty_fc = EnsembleForecast(
            city_key="nyc",
            city_name="New York City",
            target_date=date(2026, 10, 28),
            member_highs=[],
            member_lows=[],
        )
        self.assertEqual(empty_fc.probability_high_above(70.0), 0.5)
        self.assertEqual(empty_fc.probability_high_below(70.0), 0.5)
        self.assertEqual(empty_fc.probability_high_between(70.0, 71.0), 0.20)
        self.assertEqual(empty_fc.probability_low_above(50.0), 0.5)
        self.assertEqual(empty_fc.probability_low_below(50.0), 0.5)
        self.assertEqual(empty_fc.probability_low_between(50.0, 51.0), 0.20)

    def test_icao_station_coordinates_and_utc_offsets(self):
        """Verify CITY_CONFIG pins official NWS ICAO climate stations and local standard UTC offsets."""
        from backend.data.weather import CITY_CONFIG

        expected = {
            "nyc": ("KNYC", 40.7789, -73.9692, -5),
            "chicago": ("KORD", 41.9742, -87.9073, -6),
            "miami": ("KMIA", 25.7959, -80.2870, -5),
            "los_angeles": ("KLAX", 33.9425, -118.4081, -8),
            "denver": ("KDEN", 39.8561, -104.6737, -7),
            "austin": ("KATT", 30.3208, -97.7604, -6),
            "houston": ("KIAH", 29.9902, -95.3368, -6),
        }
        for city_key, (station, lat, lon, offset) in expected.items():
            self.assertIn(city_key, CITY_CONFIG)
            cfg = CITY_CONFIG[city_key]
            self.assertEqual(cfg["nws_station"], station)
            self.assertAlmostEqual(cfg["lat"], lat, places=3)
            self.assertAlmostEqual(cfg["lon"], lon, places=3)
            self.assertEqual(cfg["utc_offset"], offset)
            self.assertIn("tz", cfg)

    def test_nws_local_midnight_and_obs_cache(self):
        """
        Verify fetch_nws_observed_temperature queries from local midnight (not 00:00:00Z)
        and caches results in _obs_cache to avoid redundant HTTP requests.
        """
        import asyncio
        from datetime import date
        from unittest.mock import patch, AsyncMock, MagicMock
        import backend.data.weather as weather_mod

        weather_mod._obs_cache.clear()
        target = date(2026, 10, 28)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "features": [
                {"properties": {"temperature": {"value": 20.0}}},  # 68.0F
                {"properties": {"temperature": {"value": 25.0}}},  # 77.0F
            ]
        }

        mock_get = AsyncMock(return_value=mock_resp)

        async def run_check():
            with patch("httpx.AsyncClient.get", mock_get):
                # First call for Los Angeles (utc_offset = -8 -> local midnight is 08:00:00Z)
                obs1 = await weather_mod.fetch_nws_observed_temperature("los_angeles", target)
                self.assertIsNotNone(obs1)
                self.assertAlmostEqual(obs1["high"], 77.0)
                self.assertAlmostEqual(obs1["low"], 68.0)
                self.assertEqual(mock_get.call_count, 1)

                # Verify start parameter uses 08:00:00Z (local midnight), NOT 00:00:00Z
                call_kwargs = mock_get.call_args.kwargs
                self.assertEqual(call_kwargs["params"]["start"], "2026-10-28T08:00:00Z")
                self.assertEqual(call_kwargs["params"]["end"], "2026-10-29T08:00:00Z")

                # Second call must hit _obs_cache without issuing another HTTP request
                obs2 = await weather_mod.fetch_nws_observed_temperature("los_angeles", target)
                self.assertEqual(obs2, obs1)
                self.assertEqual(mock_get.call_count, 1)

        asyncio.run(run_check())

    def test_weather_signal_ratchet_and_single_db_session(self):
        """
        Verify:
          1. C-137 ASOS High-Water Mark Ratchet uses +/-0.5F NWS integer rounding rules:
             - For 'between' [70, 71], observed high 71.2F does NOT lock NO (rounds to 71F),
               while observed high 71.6F (>= 71.5F) locks NO (0.001).
             - For 'above' 71, observed high 71.2F does NOT lock YES, while 71.6F locks YES (0.999).
             - For 'below' 70, observed high 69.6F (>= 69.5F) locks NO (0.001).
          2. scan_for_weather_signals queries BotState once outside the per-market loop.
        """
        import asyncio
        from datetime import date
        from unittest.mock import patch, AsyncMock, MagicMock
        from backend.data.weather import EnsembleForecast
        from backend.data.weather_markets import WeatherMarket
        import backend.core.weather_signals as ws_mod

        today = date.today()
        mock_fc = EnsembleForecast(
            city_key="nyc",
            city_name="New York City",
            target_date=today,
            member_highs=[70.0, 70.5, 71.0, 71.2, 72.0] * 10,
            member_lows=[55.0] * 50,
        )

        m_between = WeatherMarket(
            slug="KXHIGHNY-TEST-B70.5",
            market_id="KXHIGHNY-TEST-B70.5",
            platform="kalshi",
            title="NYC high 70-71F",
            city_key="nyc",
            city_name="New York City",
            target_date=today,
            threshold_f=70.0,
            cap_f=71.0,
            metric="high",
            direction="between",
            yes_price=0.40,
            no_price=0.60,
        )

        m_above = WeatherMarket(
            slug="KXHIGHNY-TEST-T71",
            market_id="KXHIGHNY-TEST-T71",
            platform="kalshi",
            title="NYC high >71F",
            city_key="nyc",
            city_name="New York City",
            target_date=today,
            threshold_f=71.0,
            metric="high",
            direction="above",
            yes_price=0.40,
            no_price=0.60,
        )

        async def run_ratchet_checks():
            # Case A: Observed high is 71.2F (rounds to 71F -> still inside [70, 71], not > 71)
            with patch.object(ws_mod, "fetch_ensemble_forecast", AsyncMock(return_value=mock_fc)), \
                 patch.object(ws_mod, "fetch_nws_observed_temperature", AsyncMock(return_value={"high": 71.2, "low": 55.0})):
                sig_bet_712 = await ws_mod.generate_weather_signal(m_between, bankroll=50.0)
                self.assertGreater(sig_bet_712.model_probability, 0.50, "71.2F rounds to 71F and must NOT lock NO on 70-71F bracket")

                sig_abv_712 = await ws_mod.generate_weather_signal(m_above, bankroll=50.0)
                self.assertLess(sig_abv_712.model_probability, 0.99, "71.2F rounds to 71F and must NOT lock YES on >71F strike")

            # Case B: Observed high is 71.6F (rounds to 72F -> busts [70, 71] and locks > 71)
            with patch.object(ws_mod, "fetch_ensemble_forecast", AsyncMock(return_value=mock_fc)), \
                 patch.object(ws_mod, "fetch_nws_observed_temperature", AsyncMock(return_value={"high": 71.6, "low": 55.0})):
                sig_bet_716 = await ws_mod.generate_weather_signal(m_between, bankroll=50.0)
                self.assertAlmostEqual(sig_bet_716.model_probability, 0.001, places=4)

                sig_abv_716 = await ws_mod.generate_weather_signal(m_above, bankroll=50.0)
                self.assertAlmostEqual(sig_abv_716.model_probability, 0.999, places=4)

            # Verify scan_for_weather_signals opens SessionLocal only once for bankroll lookup across multiple markets
            mock_session = MagicMock()
            mock_state = MagicMock()
            mock_state.bankroll = 50.0
            mock_session.query.return_value.first.return_value = mock_state

            with patch.object(ws_mod, "SessionLocal", return_value=mock_session) as mock_session_cls, \
                 patch.object(ws_mod, "fetch_polymarket_weather_markets", AsyncMock(return_value=[m_between, m_above])), \
                 patch("backend.data.kalshi_markets.fetch_kalshi_weather_markets", AsyncMock(return_value=[])), \
                 patch.object(ws_mod, "fetch_ensemble_forecast", AsyncMock(return_value=mock_fc)), \
                 patch.object(ws_mod, "fetch_nws_observed_temperature", AsyncMock(return_value={"high": 70.0, "low": 55.0})), \
                 patch.object(ws_mod, "_persist_weather_signals", MagicMock()):
                signals = await ws_mod.scan_for_weather_signals()
                self.assertEqual(len(signals), 2)
                self.assertEqual(mock_session_cls.call_count, 1, "SessionLocal must be opened only once before the market loop")

        asyncio.run(run_ratchet_checks())

    def test_weather_no_edge_spread_and_bracket_agreement(self):
        """
        Verify:
          1. NO edge is computed against actual market.no_price (not 1 - market.yes_price).
          2. Wide bid-ask spreads (> 10c) are filtered out (edge = 0.0, passes_threshold = False).
          3. Unanimous bracket members straddling floor_f (e.g. 71.8F and 72.2F in [72, 73])
             produce 100% agreement (confidence = 0.90), not 50% from splitting at threshold_f.
        """
        import asyncio
        from datetime import date, timedelta
        from unittest.mock import patch, AsyncMock
        from backend.data.weather import EnsembleForecast
        from backend.data.weather_markets import WeatherMarket
        import backend.core.weather_signals as ws_mod

        tomorrow = date.today() + timedelta(days=1)
        # All 20 members land in [71.5, 73.5) -> 100% in 72-73F bracket, 0% in 86-87F bracket
        fc = EnsembleForecast(
            city_key="chicago",
            city_name="Chicago",
            target_date=tomorrow,
            member_highs=[71.8] * 10 + [72.2] * 10,
            member_lows=[55.0] * 20,
        )

        # Market 1: 72-73F bracket where all members are inside [71.5, 73.5)
        m_unanimous_bracket = WeatherMarket(
            slug="KXHIGHCHI-TEST-B72.5",
            market_id="KXHIGHCHI-TEST-B72.5",
            platform="kalshi",
            title="Chicago high 72-73F",
            city_key="chicago",
            city_name="Chicago",
            target_date=tomorrow,
            threshold_f=72.0,
            cap_f=73.0,
            metric="high",
            direction="between",
            yes_price=0.40,
            no_price=0.60,
        )

        # Market 2: 86-87F bracket with 8c spread (yes_ask=0.67, no_ask=0.41 -> spread=0.08 <= 0.10)
        m_no_with_spread = WeatherMarket(
            slug="KXHIGHMIA-TEST-B86.5",
            market_id="KXHIGHMIA-TEST-B86.5",
            platform="kalshi",
            title="Miami high 86-87F",
            city_key="chicago",
            city_name="Chicago",
            target_date=tomorrow,
            threshold_f=86.0,
            cap_f=87.0,
            metric="high",
            direction="between",
            yes_price=0.67,
            no_price=0.41,
        )

        # Market 3: Illiquid 16c spread (yes_ask=0.57, no_ask=0.59 -> spread=0.16 > 0.10)
        m_wide_spread = WeatherMarket(
            slug="KXHIGHMIA-TEST-B87.5",
            market_id="KXHIGHMIA-TEST-B87.5",
            platform="kalshi",
            title="Miami high 87-88F",
            city_key="chicago",
            city_name="Chicago",
            target_date=tomorrow,
            threshold_f=87.0,
            cap_f=88.0,
            metric="high",
            direction="between",
            yes_price=0.57,
            no_price=0.59,
        )

        async def run_checks():
            with patch.object(ws_mod, "fetch_ensemble_forecast", AsyncMock(return_value=fc)):
                sig1 = await ws_mod.generate_weather_signal(m_unanimous_bracket, bankroll=50.0)
                self.assertAlmostEqual(sig1.confidence, 0.90, places=4)
                self.assertIn("72-73F", sig1.reasoning)
                self.assertIn("Agreement: 100%", sig1.reasoning)

                sig2 = await ws_mod.generate_weather_signal(m_no_with_spread, bankroll=50.0)
                self.assertEqual(sig2.direction, "no")
                # True NO edge with [0.15, 0.85] tail clipping = (1.0 - 0.15) - 0.41 = 0.44
                self.assertAlmostEqual(sig2.edge, 0.44, places=4)

                sig3 = await ws_mod.generate_weather_signal(m_wide_spread, bankroll=50.0)
                self.assertEqual(sig3.edge, 0.0)
                self.assertFalse(sig3.passes_threshold)
                self.assertIn("spread 16% > 10%", sig3.reasoning)

                # Market 4: 0/82 longshot at yes_price=0.04, no_price=0.98 must produce edge == 0.0
                # (NOT a fake +11% YES edge from flooring model_yes_prob at 0.15)
                fc_82 = EnsembleForecast(
                    city_key="houston",
                    city_name="Houston",
                    target_date=tomorrow,
                    member_highs=[77.9] * 82,
                    member_lows=[62.0] * 82,
                )
                m_tail_longshot = WeatherMarket(
                    slug="KXHIGHTHOU-26OCT30-T85",
                    market_id="KXHIGHTHOU-26OCT30-T85",
                    platform="kalshi",
                    title="Houston high >85F",
                    city_key="houston",
                    city_name="Houston",
                    target_date=tomorrow,
                    threshold_f=85.0,
                    metric="high",
                    direction="above",
                    yes_price=0.04,
                    no_price=0.98,
                )
                # Market 5: 82/82 lock at yes_price=0.96, no_price=0.05 must also produce edge == 0.0
                # (NOT a fake +10% NO edge from capping YES at 0.85 -> 0.15 NO floor)
                m_tail_favorite = WeatherMarket(
                    slug="KXHIGHTHOU-26OCT30-T70",
                    market_id="KXHIGHTHOU-26OCT30-T70",
                    platform="kalshi",
                    title="Houston high >70F",
                    city_key="houston",
                    city_name="Houston",
                    target_date=tomorrow,
                    threshold_f=70.0,
                    metric="high",
                    direction="above",
                    yes_price=0.96,
                    no_price=0.05,
                )
            with patch.object(ws_mod, "fetch_ensemble_forecast", AsyncMock(return_value=fc_82)):
                sig_longshot = await ws_mod.generate_weather_signal(m_tail_longshot, bankroll=50.0)
                self.assertEqual(sig_longshot.edge, 0.0, "0/82 longshot at yes_price=0.04, no_price=0.98 must have 0.0 edge")
                self.assertAlmostEqual(sig_longshot.model_probability, 0.0, places=4)
                self.assertFalse(sig_longshot.passes_threshold)

                sig_fav = await ws_mod.generate_weather_signal(m_tail_favorite, bankroll=50.0)
                self.assertEqual(sig_fav.edge, 0.0, "82/82 favorite at yes_price=0.96, no_price=0.05 must have 0.0 edge")
                self.assertFalse(sig_fav.passes_threshold)

        asyncio.run(run_checks())

    def test_settlement_directional_brier_and_weather_signal_outcome(self):
        """
        Verify settle_pending_trades:
          1. Computes directional win probability (1 - model_probability for 'down'/'no' trades)
             when recording to calibration_harness so winning DOWN/NO trades get low Brier scores.
          2. Maps settlement_value to 'yes'/'no' (not 'up'/'down') when updating linked weather signals.
        """
        import asyncio
        from unittest.mock import patch, AsyncMock, MagicMock
        import backend.core.settlement as settle_mod
        from backend.analytics.calibration import SettlementCalibrationHarness

        temp_harness = SettlementCalibrationHarness(
            journal_path="/tmp/test_c137_settle_journal.jsonl",
            brier_threshold=0.245,
            min_trades_for_audit=3,
        )
        temp_harness.settled_records.clear()
        temp_harness.category_records = {"btc": [], "weather": [], "general": []}
        temp_harness.locked_categories.clear()

        # Winning NO weather trade: model_probability (YES) = 0.10 -> NO win prob = 0.90
        mock_trade = MagicMock()
        mock_trade.id = 999
        mock_trade.market_ticker = "KXHIGHNY-TEST-B70.5"
        mock_trade.platform = "kalshi"
        mock_trade.market_type = "weather"
        mock_trade.direction = "no"
        mock_trade.entry_price = 0.40
        mock_trade.size = 2.0
        mock_trade.model_probability = 0.10
        mock_trade.settled = False
        mock_trade.signal_id = 777

        mock_signal = MagicMock()
        mock_signal.id = 777
        mock_signal.market_type = "weather"
        mock_signal.direction = "no"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_trade]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_signal

        async def run_settle():
            # Market resolves NO (settlement_value = 0.0 -> NO trade wins!)
            with patch.object(settle_mod, "check_weather_settlement", AsyncMock(return_value=(True, 0.0, 2.95))), \
                 patch.object(settle_mod, "calibration_harness", temp_harness):
                settled = await settle_mod.settle_pending_trades(mock_db)
                self.assertEqual(len(settled), 1)
                self.assertEqual(mock_trade.result, "win")
                # Weather signal outcome must be 'no' and outcome_correct must be True
                self.assertEqual(mock_signal.actual_outcome, "no")
                self.assertTrue(mock_signal.outcome_correct)
                # Calibration harness must record predicted_prob = 0.90 (1 - 0.10), Brier = (0.90 - 1.0)^2 = 0.01
                brier = temp_harness.get_category_brier("weather")
                self.assertAlmostEqual(brier, 0.01, places=4)

        asyncio.run(run_settle())

    def test_kalshi_v2_create_order_yes_leg_and_auth_hygiene(self):
        """
        Verify Kalshi V2 CreateOrderV2Request single-book YES-leg specification:
          - Buying 'yes' at 0.35 -> side='bid', price='0.3500', no 'type' field
          - Buying 'no' at 0.42  -> side='ask', price='0.5800' (1.0 - 0.42), no 'type' field
          - Default time_in_force='immediate_or_cancel'
          - _sign_request strips query parameters from path before signing
        """
        import asyncio
        from unittest.mock import patch, AsyncMock
        from backend.data.kalshi_client import KalshiClient

        client = KalshiClient()

        async def run_order_checks():
            mock_post = AsyncMock(return_value={"order_id": "ord-123", "fill_count": 5})
            with patch.object(client, "post", mock_post):
                # 1. Buy YES at $0.35
                await client.create_order(
                    ticker="KXHIGHNY-26OCT29-B60.5",
                    contract_type="yes",
                    count=5,
                    price_dollars=0.35,
                )
                path_yes, payload_yes = mock_post.call_args.args
                self.assertEqual(path_yes, "/portfolio/events/orders")
                self.assertNotIn("type", payload_yes)
                self.assertEqual(payload_yes["side"], "bid")
                self.assertEqual(payload_yes["price"], "0.3500")
                self.assertEqual(payload_yes["count"], "5")
                self.assertEqual(payload_yes["time_in_force"], "immediate_or_cancel")

                # 2. Buy NO at $0.42 -> converts to YES ask at $0.5800
                await client.create_order(
                    ticker="KXHIGHCHI-26OCT29-B76.5",
                    contract_type="no",
                    count=3,
                    price_dollars=0.42,
                )
                path_no, payload_no = mock_post.call_args.args
                self.assertEqual(path_no, "/portfolio/events/orders")
                self.assertNotIn("type", payload_no)
                self.assertEqual(payload_no["side"], "ask")
                self.assertEqual(payload_no["price"], "0.5800")
                self.assertEqual(payload_no["count"], "3")
                self.assertEqual(payload_no["time_in_force"], "immediate_or_cancel")

        asyncio.run(run_order_checks())

        # Verify _sign_request strips query params (Ed25519) and uses PSS.DIGEST_LENGTH (RSA)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        from cryptography.hazmat.primitives import hashes
        import base64
        priv = Ed25519PrivateKey.generate()
        with patch.object(client, "_load_private_key", return_value=priv):
            headers = client._sign_request("GET", "/trade-api/v2/markets?series_ticker=KXHIGHNY&limit=200")
            sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
            ts = headers["KALSHI-ACCESS-TIMESTAMP"]
            # Must verify against path WITHOUT query string
            expected_msg = f"{ts}GET/trade-api/v2/markets".encode("utf-8")
            priv.public_key().verify(sig, expected_msg)

        rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with patch.object(client, "_load_private_key", return_value=rsa_priv):
            headers_rsa = client._sign_request("POST", "/trade-api/v2/portfolio/events/orders?foo=bar")
            sig_rsa = base64.b64decode(headers_rsa["KALSHI-ACCESS-SIGNATURE"])
            ts_rsa = headers_rsa["KALSHI-ACCESS-TIMESTAMP"]
            expected_msg_rsa = f"{ts_rsa}POST/trade-api/v2/portfolio/events/orders".encode("utf-8")
            rsa_priv.public_key().verify(
                sig_rsa,
                expected_msg_rsa,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256(),
            )

    def test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book(self):
        """
        Verify:
          1. CITY_SERIES['houston'] == 'KXHIGHTHOU'
          2. _parse_kalshi_market handles negative temperature strikes (e.g. -5, -12.5)
          3. _parse_kalshi_market handles 'greater_or_equal' (floor - 1.0) and 'less_or_equal' (cap + 1.0)
          4. One-sided empty-book markets (yes_ask_dollars='1.0000', no_ask_dollars='0.3500') are retained
             and not falsely rejected by the 10% spread filter when trading the liquid NO side.
        """
        import asyncio
        from datetime import date, timedelta
        from unittest.mock import patch, AsyncMock
        from backend.data.kalshi_markets import CITY_SERIES, _parse_kalshi_market, fetch_kalshi_weather_markets
        from backend.data.weather import EnsembleForecast
        import backend.core.weather_signals as ws_mod

        self.assertEqual(CITY_SERIES["houston"], "KXHIGHTHOU")

        # Negative strike with 'less'
        p_neg = _parse_kalshi_market(
            {"ticker": "KXHIGHCHI-26JAN15-T-5", "strike_type": "less", "cap_strike": -5.0},
            "chicago",
        )
        self.assertIsNotNone(p_neg)
        self.assertEqual(p_neg["direction"], "below")
        self.assertEqual(p_neg["threshold_f"], -5.0)

        # Inclusive 'greater_or_equal' (>= 80F is equivalent to > 79F)
        p_ge = _parse_kalshi_market(
            {"ticker": "KXHIGHTHOU-26OCT29-T80", "strike_type": "greater_or_equal", "floor_strike": 80.0},
            "houston",
        )
        self.assertIsNotNone(p_ge)
        self.assertEqual(p_ge["direction"], "above")
        self.assertEqual(p_ge["threshold_f"], 79.0)

        # Inclusive 'less_or_equal' (<= 50F is equivalent to < 51F)
        p_le = _parse_kalshi_market(
            {"ticker": "KXHIGHTHOU-26OCT29-T50", "strike_type": "less_or_equal", "cap_strike": 50.0},
            "houston",
        )
        self.assertIsNotNone(p_le)
        self.assertEqual(p_le["direction"], "below")
        self.assertEqual(p_le["threshold_f"], 51.0)

        # One-sided empty book (yes_ask_dollars == "1.0000", no_ask_dollars == "0.3500")
        tomorrow = date.today() + timedelta(days=1)
        mon_abbr = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"][tomorrow.month - 1]
        tkr = f"KXHIGHTHOU-{tomorrow.year % 100:02d}{mon_abbr}{tomorrow.day:02d}-B85.5"

        mock_raw_market = {
            "ticker": tkr,
            "title": "Houston high 85-86F",
            "strike_type": "between",
            "floor_strike": 85.0,
            "cap_strike": 86.0,
            "yes_ask_dollars": "1.0000",
            "no_ask_dollars": "0.3500",
            "last_price_dollars": "0.0000",
            "volume_fp": "12.00",
        }

        fc = EnsembleForecast(
            city_key="houston",
            city_name="Houston",
            target_date=tomorrow,
            member_highs=[75.0] * 30,  # 0/30 in 85-86F -> clipped model_yes_prob = 0.15, NO prob = 0.85
            member_lows=[60.0] * 30,
        )

        tkr_two_sided_empty = f"KXHIGHTHOU-{tomorrow.year % 100:02d}{mon_abbr}{tomorrow.day:02d}-T90"
        mock_two_sided_empty = {
            "ticker": tkr_two_sided_empty,
            "title": "Houston high >90F (empty book, zero last price)",
            "strike_type": "greater",
            "floor_strike": 90.0,
            "yes_ask_dollars": "1.0000",
            "no_ask_dollars": "1.0000",
            "last_price_dollars": "0.0000",
            "volume_fp": "0.00",
        }
        tkr_two_sided_stale_last = f"KXHIGHTHOU-{tomorrow.year % 100:02d}{mon_abbr}{tomorrow.day:02d}-T92"
        mock_two_sided_stale_last = {
            "ticker": tkr_two_sided_stale_last,
            "title": "Houston high >92F (empty book, historical last price)",
            "strike_type": "greater",
            "floor_strike": 92.0,
            "yes_ask_dollars": "1.0000",
            "no_ask_dollars": "1.0000",
            "last_price_dollars": "0.4500",
            "volume_fp": "5.00",
        }

        tkr_minimal_liquid_last = f"KXHIGHTHOU-{tomorrow.year % 100:02d}{mon_abbr}{tomorrow.day:02d}-T94"
        mock_minimal_liquid_last = {
            "ticker": tkr_minimal_liquid_last,
            "title": "Houston high >94F (no ask fields / None ask, liquid last price)",
            "strike_type": "greater",
            "floor_strike": 94.0,
            "yes_ask_dollars": None,
            "last_price_dollars": "0.3000",
        }
        tkr_minimal_zero_last = f"KXHIGHTHOU-{tomorrow.year % 100:02d}{mon_abbr}{tomorrow.day:02d}-T96"
        mock_minimal_zero_last = {
            "ticker": tkr_minimal_zero_last,
            "title": "Houston high >96F (no ask fields, zero last price)",
            "strike_type": "greater",
            "floor_strike": 96.0,
            "last_price_dollars": "0.0000",
        }

        async def run_empty_book_check():
            with patch(
                "backend.data.kalshi_markets.KalshiClient.get_markets",
                AsyncMock(
                    return_value={
                        "markets": [
                            mock_raw_market,
                            mock_two_sided_empty,
                            mock_two_sided_stale_last,
                            mock_minimal_liquid_last,
                            mock_minimal_zero_last,
                        ],
                        "cursor": "",
                    }
                ),
            ):
                mkts = await fetch_kalshi_weather_markets(["houston"])
                self.assertEqual(
                    len(mkts),
                    2,
                    "One-sided market and minimal mock with liquid last_price must be retained; two-sided empty-book and zero-price markets must be skipped",
                )
                self.assertEqual(mkts[0].slug, tkr)
                self.assertEqual(mkts[0].yes_price, 1.0)
                self.assertEqual(mkts[0].no_price, 0.35)
                self.assertEqual(mkts[1].slug, tkr_minimal_liquid_last)
                self.assertEqual(mkts[1].yes_price, 0.30)
                self.assertEqual(mkts[1].no_price, 0.70)

                with patch.object(ws_mod, "fetch_ensemble_forecast", AsyncMock(return_value=fc)):
                    sig = await ws_mod.generate_weather_signal(mkts[0], bankroll=50.0)
                    self.assertIsNotNone(sig)
                    self.assertEqual(sig.direction, "no")
                    self.assertAlmostEqual(sig.model_probability, 0.15, places=4)
                    self.assertAlmostEqual(sig.edge, 0.85 - 0.35, places=4)
                    self.assertTrue(sig.passes_threshold, "Liquid side of one-sided market must pass threshold without spread penalty")

                # Verify MonotonicityScanner does not emit a false arbitrage inversion when a higher strike has yes_price=1.0 sentinel
                from backend.analytics.monotonicity import monotonicity_scanner
                from backend.data.weather_markets import WeatherMarket
                lower_mkt = WeatherMarket(
                    slug="KXHIGHTHOU-TEST-T80",
                    market_id="KXHIGHTHOU-TEST-T80",
                    platform="kalshi",
                    title="Houston high >80F",
                    city_key="houston",
                    city_name="Houston",
                    target_date=tomorrow,
                    threshold_f=80.0,
                    metric="high",
                    direction="above",
                    yes_price=0.60,
                    no_price=0.42,
                )
                higher_empty_yes = WeatherMarket(
                    slug="KXHIGHTHOU-TEST-T85",
                    market_id="KXHIGHTHOU-TEST-T85",
                    platform="kalshi",
                    title="Houston high >85F",
                    city_key="houston",
                    city_name="Houston",
                    target_date=tomorrow,
                    threshold_f=85.0,
                    metric="high",
                    direction="above",
                    yes_price=1.0,
                    no_price=0.25,
                )
                self.assertEqual(monotonicity_scanner.check_ladder_monotonicity([lower_mkt, higher_empty_yes]), [])

        asyncio.run(run_empty_book_check())

    def test_scheduler_fill_verification_and_kalshi_finalized_settlement(self):
        """
        Verify:
          1. weather_scan_and_trade_job does NOT insert phantom Trade when create_order raises or fill_count == 0,
             and preserves event_slug=signal.market.slug when filled (including via fill_count_fp when fill_count is None/0).
          2. _fetch_kalshi_resolution requires status == 'finalized' (rejects 'determined') and supports
             settlement_value_dollars and legacy settlement_value fallbacks.
          3. Production trade_journal.jsonl has weather category unlocked (Brier < 0.2450).
        """
        import asyncio
        from datetime import date, timedelta
        from unittest.mock import patch, AsyncMock, MagicMock
        import backend.core.scheduler as sched_mod
        import backend.core.settlement as settle_mod
        from backend.data.weather_markets import WeatherMarket
        from backend.core.weather_signals import WeatherTradingSignal
        from backend.analytics.calibration import calibration_harness

        # Verify live calibration_harness weather category is unlocked
        permitted, reason = calibration_harness.is_category_permitted("weather")
        self.assertTrue(permitted, f"Weather category must be unlocked in trade_journal.jsonl, got: {reason}")
        wx_brier = calibration_harness.get_category_brier("weather")
        self.assertIsNotNone(wx_brier)
        self.assertLess(wx_brier, 0.245)

        tomorrow = date.today() + timedelta(days=1)
        mkt = WeatherMarket(
            slug="KXHIGHTHOU-26OCT29-B80.5",
            market_id="KXHIGHTHOU-26OCT29-B80.5",
            platform="kalshi",
            title="Houston high 80-81F",
            city_key="houston",
            city_name="Houston",
            target_date=tomorrow,
            threshold_f=80.0,
            cap_f=81.0,
            metric="high",
            direction="between",
            yes_price=0.60,
            no_price=0.40,
        )
        sig = WeatherTradingSignal(
            market=mkt,
            model_probability=0.15,
            market_probability=0.60,
            edge=0.45,
            direction="no",
            confidence=0.90,
            kelly_fraction=0.04,
            suggested_size=2.00,
        )

        async def run_scheduler_and_settlement_checks():
            # A0. create_order raises exception -> must NOT call db.add(trade)
            mock_db = MagicMock()
            mock_state = MagicMock(bankroll=50.0, is_running=True, total_trades=0)
            mock_db.query.return_value.first.return_value = mock_state
            mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0
            mock_db.query.return_value.filter.return_value.first.return_value = None

            with patch.object(sched_mod.settings, "KALSHI_EXECUTE_DEMO_ORDERS", True), \
                 patch("backend.core.weather_signals.scan_for_weather_signals", AsyncMock(return_value=[sig])), \
                 patch.object(sched_mod, "SessionLocal", return_value=mock_db), \
                 patch.object(sched_mod, "PaperSessionLocal", return_value=MagicMock()), \
                 patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.create_order", AsyncMock(side_effect=ValueError("400 invalid_parameters"))):
                await sched_mod.weather_scan_and_trade_job()
                self.assertEqual(mock_db.add.call_count, 0, "Failed order placement must not insert phantom Trade")

            # A. Unfilled IOC order (fill_count=0) -> must NOT call db.add(trade)
            with patch.object(sched_mod.settings, "KALSHI_EXECUTE_DEMO_ORDERS", True), \
                 patch("backend.core.weather_signals.scan_for_weather_signals", AsyncMock(return_value=[sig])), \
                 patch.object(sched_mod, "SessionLocal", return_value=mock_db), \
                 patch.object(sched_mod, "PaperSessionLocal", return_value=MagicMock()), \
                 patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.create_order", AsyncMock(return_value={"order": {"order_id": "ord-unfilled", "fill_count": 0}})):
                await sched_mod.weather_scan_and_trade_job()
                self.assertEqual(mock_db.add.call_count, 0, "Unfilled IOC order must not insert phantom Trade")

            # B. Filled IOC order with fill_count=None and fill_count_fp="4.00" @ $0.40 -> size=$1.60, preserves event_slug
            with patch.object(sched_mod.settings, "KALSHI_EXECUTE_DEMO_ORDERS", True), \
                 patch("backend.core.weather_signals.scan_for_weather_signals", AsyncMock(return_value=[sig])), \
                 patch.object(sched_mod, "SessionLocal", return_value=mock_db), \
                 patch.object(sched_mod, "PaperSessionLocal", return_value=MagicMock()), \
                 patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.create_order", AsyncMock(return_value={"order": {"order_id": "ord-filled", "fill_count": None, "fill_count_fp": "4.00"}})):
                await sched_mod.weather_scan_and_trade_job()
                self.assertEqual(mock_db.add.call_count, 1)
                inserted_trade = mock_db.add.call_args.args[0]
                self.assertEqual(inserted_trade.event_slug, "KXHIGHTHOU-26OCT29-B80.5")
                self.assertAlmostEqual(inserted_trade.size, 1.60, places=2)

            # B2. When top 3 actionable signals are already held, the 4th actionable signal must still execute
            held_sigs = []
            for idx in range(3):
                m_held = WeatherMarket(
                    slug=f"KXHIGHTHOU-HELD-{idx}",
                    market_id=f"KXHIGHTHOU-HELD-{idx}",
                    platform="kalshi",
                    title=f"Held {idx}",
                    city_key="houston",
                    city_name="Houston",
                    target_date=tomorrow,
                    threshold_f=80.0 + idx,
                    metric="high",
                    direction="above",
                    yes_price=0.40,
                    no_price=0.60,
                )
                held_sigs.append(
                    WeatherTradingSignal(
                        market=m_held,
                        model_probability=0.85,
                        market_probability=0.40,
                        edge=0.45 - idx * 0.01,
                        direction="yes",
                        confidence=0.90,
                        kelly_fraction=0.04,
                        suggested_size=2.00,
                    )
                )
            mock_db_b2 = MagicMock()
            mock_db_b2.query.return_value.first.return_value = MagicMock(bankroll=50.0, is_running=True, total_trades=0)
            mock_db_b2.query.return_value.filter.return_value.scalar.return_value = 0.0
            # First 3 Trade existence checks return an existing Trade; 4th returns None, subsequent checks return None
            mock_db_b2.query.return_value.filter.return_value.first.side_effect = [MagicMock(), MagicMock(), MagicMock(), None] + [None] * 10

            with patch.object(sched_mod.settings, "KALSHI_EXECUTE_DEMO_ORDERS", True), \
                 patch("backend.core.weather_signals.scan_for_weather_signals", AsyncMock(return_value=held_sigs + [sig])), \
                 patch.object(sched_mod, "SessionLocal", return_value=mock_db_b2), \
                 patch.object(sched_mod, "PaperSessionLocal", return_value=MagicMock()), \
                 patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.create_order", AsyncMock(return_value={"order": {"order_id": "ord-4th", "fill_count": 5}})):
                await sched_mod.weather_scan_and_trade_job()
                self.assertEqual(mock_db_b2.add.call_count, 1, "4th actionable signal must execute when top 3 are already held")
                self.assertEqual(mock_db_b2.add.call_args.args[0].market_ticker, "KXHIGHTHOU-26OCT29-B80.5")

            # C. _fetch_kalshi_resolution requires 'finalized'
            with patch("backend.data.kalshi_client.KalshiClient.get_market", AsyncMock(return_value={"market": {"status": "determined", "result": "yes"}})):
                resolved, val = await settle_mod._fetch_kalshi_resolution("KXHIGHTHOU-26OCT29-B80.5")
                self.assertFalse(resolved)
                self.assertIsNone(val)

            with patch("backend.data.kalshi_client.KalshiClient.get_market", AsyncMock(return_value={"market": {"status": "finalized", "result": "", "settlement_value_dollars": "1.0000"}})):
                resolved, val = await settle_mod._fetch_kalshi_resolution("KXHIGHTHOU-26OCT29-B80.5")
                self.assertTrue(resolved)
                self.assertEqual(val, 1.0)

            with patch("backend.data.kalshi_client.KalshiClient.get_market", AsyncMock(return_value={"market": {"status": "finalized", "result": "", "settlement_value_dollars": None, "settlement_value": 0}})):
                resolved, val = await settle_mod._fetch_kalshi_resolution("KXHIGHTHOU-26OCT29-B80.5")
                self.assertTrue(resolved)
                self.assertEqual(val, 0.0)

            # D. reset_bot falls back to balance / 100.0 when balance_dollars is None
            import backend.api.main as main_mod
            mock_reset_db = MagicMock()
            mock_reset_state = MagicMock()
            mock_reset_db.query.return_value.first.return_value = mock_reset_state
            with patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.get_balance", AsyncMock(return_value={"balance_dollars": None, "balance": 4567})):
                res = await main_mod.reset_bot(db=mock_reset_db)
                self.assertAlmostEqual(res["new_bankroll"], 45.67, places=2)
                self.assertAlmostEqual(mock_reset_state.bankroll, 45.67, places=2)

        asyncio.run(run_scheduler_and_settlement_checks())

    def test_fastapi_api_endpoints_qc(self):
        """Verify core API endpoints return HTTP 200 and valid JSON schemas."""
        from fastapi.testclient import TestClient
        from backend.api.main import app

        client = TestClient(app)
        for endpoint in ["/api/health", "/api/stats", "/api/trades", "/api/signals", "/api/c137/calibration"]:
            resp = client.get(endpoint)
            self.assertEqual(resp.status_code, 200, f"Endpoint {endpoint} failed with {resp.status_code}")
            self.assertIsInstance(resp.json(), (dict, list))

    def test_dual_track_weather_trading_and_paper_calibration_isolation(self):
        """
        Verify dual-track weather trading architecture:
          1. High-edge top-tier signals execute as LIVE Kalshi demo orders (is_paper=False).
          2. Signals above lower hurdle (edge >= 3%) execute as SHADOW PAPER trades (is_paper=True)
             without calling the Kalshi order API or consuming live bankroll.
          3. Settlement updates Brier scores in calibration harness for both tracks,
             while paper trade P&L never alters live bankroll.
          4. /api/stats reports live bankroll/P&L decoupled from paper stats.
        """
        import asyncio
        from datetime import date, timedelta
        from unittest.mock import patch, AsyncMock, MagicMock
        from backend.data.weather_markets import WeatherMarket
        from backend.core.weather_signals import WeatherTradingSignal
        from backend.models.database import Trade, BotState, Signal
        import backend.core.scheduler as sched_mod
        import backend.core.settlement as settle_mod
        from backend.analytics.calibration import SettlementCalibrationHarness

        tomorrow = date.today() + timedelta(days=1)
        # Top-tier signal (edge = 25% >= 8% threshold) -> Live candidate
        live_mkt = WeatherMarket(
            slug="KXHIGHTMIA-LIVE",
            market_id="KXHIGHTMIA-LIVE",
            platform="kalshi",
            title="Miami high above 85F",
            city_key="miami",
            city_name="Miami",
            target_date=tomorrow,
            threshold_f=85.0,
            metric="high",
            direction="above",
            yes_price=0.50,
            no_price=0.50,
        )
        live_sig = WeatherTradingSignal(
            market=live_mkt,
            model_probability=0.75,
            market_probability=0.50,
            edge=0.25,
            direction="yes",
            confidence=0.85,
            kelly_fraction=0.10,
            suggested_size=5.00,
        )

        # Secondary signal (edge = 5% >= 3% paper hurdle, but < 8% live threshold) -> Paper candidate
        paper_mkt = WeatherMarket(
            slug="KXHIGHTCHI-PAPER",
            market_id="KXHIGHTCHI-PAPER",
            platform="kalshi",
            title="Chicago high above 60F",
            city_key="chicago",
            city_name="Chicago",
            target_date=tomorrow,
            threshold_f=60.0,
            metric="high",
            direction="above",
            yes_price=0.45,
            no_price=0.55,
        )
        paper_sig = WeatherTradingSignal(
            market=paper_mkt,
            model_probability=0.50,
            market_probability=0.45,
            edge=0.05,
            direction="yes",
            confidence=0.60,
            kelly_fraction=0.02,
            suggested_size=1.00,
        )

        async def run_dual_track_verification():
            added_trades = []
            mock_db = MagicMock()
            mock_state = MagicMock(bankroll=100.0, total_pnl=0.0, is_running=True, total_trades=0, winning_trades=0)
            mock_db.query.return_value.first.return_value = mock_state
            mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db.add.side_effect = lambda obj: added_trades.append(obj)

            order_mock = AsyncMock(return_value={"order": {"order_id": "ord-live-1", "fill_count": 10}})
            with patch.object(sched_mod.settings, "KALSHI_EXECUTE_DEMO_ORDERS", True), \
                 patch("backend.core.weather_signals.scan_for_weather_signals", AsyncMock(return_value=[live_sig, paper_sig])), \
                 patch.object(sched_mod, "SessionLocal", return_value=mock_db), \
                 patch.object(sched_mod, "PaperSessionLocal", return_value=mock_db), \
                 patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.create_order", order_mock):
                await sched_mod.weather_scan_and_trade_job()

            # Verify: 1 Live trade and 1 Paper trade created
            self.assertEqual(len(added_trades), 2, "Must create 1 live trade and 1 paper trade")
            live_t = next(t for t in added_trades if not t.is_paper)
            paper_t = next(t for t in added_trades if t.is_paper)

            self.assertEqual(live_t.market_ticker, "KXHIGHTMIA-LIVE")
            self.assertFalse(live_t.is_paper)
            self.assertEqual(paper_t.market_ticker, "KXHIGHTCHI-PAPER")
            self.assertTrue(paper_t.is_paper)
            # Kalshi create_order must have been called ONLY ONCE (for the live trade)
            self.assertEqual(order_mock.call_count, 1)

            # Test Settlement Isolation:
            # Settle both trades: live trade wins (pnl = +$4.90), paper trade wins (pnl = +$5.50)
            live_t.pnl = 4.90
            live_t.settled = True
            live_t.result = "win"

            paper_t.pnl = 5.50
            paper_t.settled = True
            paper_t.result = "win"

            test_state = BotState(bankroll=100.0, total_pnl=0.0, total_trades=1, winning_trades=0)
            settle_db = MagicMock()
            settle_db.query.return_value.first.return_value = test_state
            settle_db.query.return_value.filter.return_value.count.return_value = 1  # 1 live win

            await settle_mod.update_bot_state_with_settlements(settle_db, [live_t, paper_t])

            # Live bankroll and P&L must ONLY increase by live trade P&L ($4.90), NOT by paper P&L ($5.50)
            self.assertAlmostEqual(test_state.bankroll, 104.90, places=2)
            self.assertAlmostEqual(test_state.total_pnl, 4.90, places=2)
            self.assertEqual(test_state.winning_trades, 1)

        asyncio.run(run_dual_track_verification())

    def test_paper_trade_does_not_block_live_trade(self):
        """
        Verify that an existing unsettled paper trade in the DB does NOT block
        subsequent top-tier live trade execution when edge expands, and the
        prior paper trade is superseded cleanly.
        """
        import asyncio
        from datetime import date, timedelta
        from unittest.mock import patch, AsyncMock, MagicMock
        from backend.data.weather_markets import WeatherMarket
        from backend.core.weather_signals import WeatherTradingSignal
        from backend.models.database import Trade
        import backend.core.scheduler as sched_mod

        tomorrow = date.today() + timedelta(days=1)
        mkt = WeatherMarket(
            slug="KXHIGHMIA-26OCT30-T85",
            market_id="KXHIGHMIA-26OCT30-T85",
            platform="kalshi",
            title="Miami high above 85F",
            city_key="miami",
            city_name="Miami",
            target_date=tomorrow,
            threshold_f=85.0,
            metric="high",
            direction="above",
            yes_price=0.50,
            no_price=0.50,
        )
        sig = WeatherTradingSignal(
            market=mkt,
            model_probability=0.80,
            market_probability=0.50,
            edge=0.30,
            direction="yes",
            confidence=0.85,
            kelly_fraction=0.10,
            suggested_size=5.00,
        )

        existing_paper_trade = Trade(
            market_ticker="KXHIGHMIA-26OCT30-T85",
            platform="kalshi",
            event_slug="KXHIGHMIA-26OCT30-T85",
            market_type="weather",
            direction="yes",
            entry_price=0.48,
            size=5.0,
            is_paper=True,
            settled=False
        )

        async def run_test():
            deleted_trades = []
            added_trades = []

            mock_db = MagicMock()
            mock_state = MagicMock(bankroll=100.0, is_running=True, total_trades=0, winning_trades=0)
            mock_db.query.return_value.first.return_value = mock_state
            mock_db.query.return_value.filter.return_value.scalar.return_value = 0.0

            # First query checks for active LIVE trade -> None (only paper exists)
            # Second query finds existing paper trade for retirement -> existing_paper_trade
            def mock_first_handler():
                # If query checks is_paper == False, return None; if is_paper == True, return existing_paper_trade
                return None
            mock_db.query.return_value.filter.return_value.first.side_effect = [None, existing_paper_trade, None, None]
            mock_db.add.side_effect = lambda obj: added_trades.append(obj)
            mock_db.delete.side_effect = lambda obj: deleted_trades.append(obj)

            order_mock = AsyncMock(return_value={"order": {"order_id": "ord-live-promo", "fill_count": 10}})
            with patch.object(sched_mod.settings, "KALSHI_EXECUTE_DEMO_ORDERS", True), \
                 patch("backend.core.weather_signals.scan_for_weather_signals", AsyncMock(return_value=[sig])), \
                 patch.object(sched_mod, "SessionLocal", return_value=mock_db), \
                 patch.object(sched_mod, "PaperSessionLocal", return_value=MagicMock()), \
                 patch("backend.data.kalshi_client.kalshi_credentials_present", return_value=True), \
                 patch("backend.data.kalshi_client.KalshiClient.create_order", order_mock):
                await sched_mod.weather_scan_and_trade_job()

            # Must have executed the live trade into SessionLocal without being blocked by PaperSessionLocal
            self.assertEqual(order_mock.call_count, 1)
            self.assertEqual(len(added_trades), 1)
            self.assertFalse(added_trades[0].is_paper)
            self.assertEqual(added_trades[0].market_ticker, "KXHIGHMIA-26OCT30-T85")

        asyncio.run(run_test())

    def test_nws_observation_weather_settlement_fallback(self):
        """
        Verify check_weather_settlement:
          - Kalshi contracts strictly require official Kalshi finalization (never settle early via NWS).
          - Polymarket contracts resolve against official NWS station observations when target date has elapsed.
        """
        import asyncio
        from unittest.mock import patch, AsyncMock
        from backend.models.database import Trade
        import backend.core.settlement as settle_mod

        # 1. Kalshi trade must NOT settle when Kalshi status is unfinalized
        kalshi_trade = Trade(
            id=41,
            market_ticker="KXHIGHTHOU-26OCT28-B80.5",
            platform="kalshi",
            event_slug="KXHIGHTHOU-26OCT28-B80.5",
            market_type="weather",
            direction="yes",
            entry_price=0.40,
            size=10.0,
            is_paper=True,
            settled=False
        )

        # 2. Polymarket trade on Houston bracket 80-81F on Oct 28 resolves via NWS fallback
        poly_trade = Trade(
            id=42,
            market_ticker="POLY-HOU-26OCT28-B80.5",
            platform="polymarket",
            event_slug="KXHIGHTHOU-26OCT28-B80.5",
            market_type="weather",
            direction="yes",
            entry_price=0.40,
            size=10.0,
            is_paper=True,
            settled=False
        )

        async def run_nws_settle():
            with patch.object(settle_mod, "_fetch_kalshi_resolution", AsyncMock(return_value=(False, None))), \
                 patch("backend.data.weather.fetch_nws_observed_temperature", AsyncMock(return_value={"high": 80.6, "low": 65.0})):
                k_settled, k_val, _ = await settle_mod.check_weather_settlement(kalshi_trade)
                self.assertFalse(k_settled, "Kalshi contract must wait for official Kalshi finalization")
                self.assertIsNone(k_val)

                # Direct NWS observation helper still parses bracket/threshold strikes for Polymarket fallback
                is_settled, settlement_val = await settle_mod._fetch_nws_resolution(kalshi_trade)

            self.assertTrue(is_settled)
            # 80.6F is between 80.0F and 81.0F -> YES wins!
            self.assertEqual(settlement_val, 1.0)

        asyncio.run(run_nws_settle())

    def test_simulate_trade_is_paper_and_stats_live_purity(self):
        """
        Verify /api/simulate-trade generates is_paper=True trades and /api/stats
        strictly reports total_trades as live trade count without paper distortion.
        """
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock
        from backend.api.main import app
        from backend.models.database import Trade, BotState, get_db

        client = TestClient(app)
        live_trade = Trade(id=1, market_ticker="LIVE-1", platform="kalshi", settled=True, result="win", pnl=5.0, is_paper=False)
        paper_trade = Trade(id=2, market_ticker="PAPER-1", platform="kalshi", settled=True, result="win", pnl=10.0, is_paper=True)
        bot_state = BotState(bankroll=100.0, total_trades=999, total_pnl=5.0, is_running=True)

        def mock_query(model):
            q = MagicMock()
            if model == BotState:
                q.first.return_value = bot_state
            elif model == Trade:
                def mock_filter(*args, **kwargs):
                    fq = MagicMock()
                    for arg in args:
                        s_arg = str(arg).lower()
                        if "is_paper = 0" in s_arg or "is_paper = false" in s_arg:
                            fq.all.return_value = [live_trade]
                            return fq
                        elif "is_paper = 1" in s_arg or "is_paper = true" in s_arg:
                            fq.all.return_value = [paper_trade]
                            return fq
                    fq.all.return_value = [live_trade]
                    return fq
                q.filter = mock_filter
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/stats")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            # total_trades must equal len(live_trades) = 1, NOT bot_state.total_trades = 999
            self.assertEqual(data["total_trades"], 1)
            self.assertEqual(data["paper_trades"], 1)
        finally:
            app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    unittest.main()
