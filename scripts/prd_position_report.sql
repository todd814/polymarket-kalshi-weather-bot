-- =============================================================================
-- C-137 PRODUCTION POSITION & WEATHER DECISION REPORT (SQLite)
-- Usage:
--   sqlite3 -header -column /opt/weather-bot/tradingbot.db < scripts/prd_position_report.sql
-- =============================================================================
.mode column
.headers on
.width 4 24 4 6 6 9 9 9 18 52 52

WITH latest_signal AS (
    SELECT
        s.market_ticker,
        s.timestamp AS latest_scan_utc,
        s.model_probability AS latest_model_yes_prob,
        s.market_price AS latest_mkt_yes_price,
        s.edge AS latest_edge,
        s.reasoning AS latest_weather_reasoning,
        ROW_NUMBER() OVER (PARTITION BY s.market_ticker ORDER BY s.timestamp DESC, s.id DESC) AS rn
    FROM signals s
    WHERE s.market_type = 'weather'
)
SELECT
    t.id AS id,
    t.market_ticker AS ticker,
    UPPER(t.direction) AS side,
    PRINTF('$%.2f', t.entry_price) AS entry,
    PRINTF('$%.2f', t.size) AS risked,
    -- Entry win probability on our held side
    PRINTF(
        '%.0f%%',
        100.0 * CASE
            WHEN LOWER(t.direction) = 'yes' THEN t.model_probability
            ELSE (1.0 - t.model_probability)
        END
    ) AS entry_win_p,
    PRINTF('%+.1f%%', 100.0 * COALESCE(t.edge_at_entry, 0.0)) AS entry_edge,
    -- Current estimated win probability on our held side from latest weather scan
    PRINTF(
        '%.0f%%',
        100.0 * CASE
            WHEN LOWER(t.direction) = 'yes' THEN COALESCE(ls.latest_model_yes_prob, t.model_probability)
            ELSE (1.0 - COALESCE(ls.latest_model_yes_prob, t.model_probability))
        END
    ) AS curr_win_p,
    -- Estimated outcome status
    CASE
        WHEN t.settled = 1 THEN UPPER(t.result) || ' (' || PRINTF('%+.2f', COALESCE(t.pnl, 0.0)) || ')'
        WHEN (
            CASE
                WHEN LOWER(t.direction) = 'yes' THEN COALESCE(ls.latest_model_yes_prob, t.model_probability)
                ELSE (1.0 - COALESCE(ls.latest_model_yes_prob, t.model_probability))
            END
        ) >= 0.90 THEN 'LOCKED WIN (RATCHET)'
        WHEN (
            CASE
                WHEN LOWER(t.direction) = 'yes' THEN COALESCE(ls.latest_model_yes_prob, t.model_probability)
                ELSE (1.0 - COALESCE(ls.latest_model_yes_prob, t.model_probability))
            END
        ) >= 0.75 THEN 'EST. WIN (STRONG)'
        WHEN (
            CASE
                WHEN LOWER(t.direction) = 'yes' THEN COALESCE(ls.latest_model_yes_prob, t.model_probability)
                ELSE (1.0 - COALESCE(ls.latest_model_yes_prob, t.model_probability))
            END
        ) >= 0.55 THEN 'EST. WIN (LEAN)'
        WHEN (
            CASE
                WHEN LOWER(t.direction) = 'yes' THEN COALESCE(ls.latest_model_yes_prob, t.model_probability)
                ELSE (1.0 - COALESCE(ls.latest_model_yes_prob, t.model_probability))
            END
        ) >= 0.45 THEN 'TOSS-UP / IN PLAY'
        ELSE 'AT RISK / TRAILING'
    END AS est_outcome,
    COALESCE(es.reasoning, 'N/A (legacy entry)') AS why_bought_weather_context,
    COALESCE(ls.latest_weather_reasoning, COALESCE(es.reasoning, 'Awaiting next scan / market closed')) AS latest_weather_context
FROM trades t
LEFT JOIN signals es
    ON es.id = t.signal_id
LEFT JOIN latest_signal ls
    ON ls.market_ticker = t.market_ticker AND ls.rn = 1
WHERE t.is_paper = 0
  AND t.market_type = 'weather'
ORDER BY t.settled ASC, t.id DESC;
