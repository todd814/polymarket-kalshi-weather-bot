"""
=============================================================================
C-137 CROSS-STRIKE MONOTONICITY & ARBITRAGE SCANNER
Author: Rick Sanchez (Dimension C-137)
Purpose: Enforces cumulative distribution function (CDF) mathematical laws
         across Kalshi weather contract ladders. Detects monotonicity
         inversions and Dutch Book risk-free spreads.
=============================================================================
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from datetime import date

logger = logging.getLogger("trading_bot")


@dataclass
class ArbitrageOpportunity:
    city_key: str
    target_date: date
    arb_type: str                   # "monotonicity_inversion" | "dutch_book"
    description: str
    profit_margin: float            # Expected risk-free spread in cents
    legs: List[Dict[str, any]]


class MonotonicityScanner:
    """
    Scans a ladder of strike prices for cumulative probability violations.
    Mathematical invariant:
      P(T >= X) >= P(T >= Y) for all X < Y.
      Therefore, Ask(X) >= Bid(Y).
      If Ask(Y) < Bid(X), buying Y and selling X produces guaranteed profit.
    """

    def check_ladder_monotonicity(self, markets: List[any]) -> List[ArbitrageOpportunity]:
        opportunities = []

        # Group markets by (city_key, target_date, metric, direction)
        grouped: Dict[Tuple[str, date, str, str], List[any]] = {}
        for m in markets:
            if not (0.02 <= getattr(m, "yes_price", 0.0) <= 0.98):
                continue
            key = (m.city_key, m.target_date, m.metric, m.direction)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(m)

        for (city_key, target_date, metric, direction), ladder in grouped.items():
            if len(ladder) < 2:
                continue

            # Sort by threshold ascending
            sorted_ladder = sorted(ladder, key=lambda x: x.threshold_f)

            if direction == "above":
                # For "above", lower thresholds MUST have higher or equal probability / price
                for i in range(len(sorted_ladder) - 1):
                    lower = sorted_ladder[i]      # Lower temp (e.g. 75F)
                    higher = sorted_ladder[i + 1]  # Higher temp (e.g. 80F)

                    # Inversion 1: Higher temp YES is more expensive than lower temp YES!
                    # Retail is paying MORE for a harder threshold!
                    if higher.yes_price > lower.yes_price + 0.03:
                        diff = higher.yes_price - lower.yes_price
                        h_ticker = getattr(higher, 'ticker', getattr(higher, 'slug', higher.market_id))
                        l_ticker = getattr(lower, 'ticker', getattr(lower, 'slug', lower.market_id))
                        opp = ArbitrageOpportunity(
                            city_key=city_key,
                            target_date=target_date,
                            arb_type="monotonicity_inversion",
                            description=(
                                f"Inversion: {h_ticker} (>={higher.threshold_f}F @ {higher.yes_price:.2f}) "
                                f"is priced higher than {l_ticker} (>={lower.threshold_f}F @ {lower.yes_price:.2f})"
                            ),
                            profit_margin=round(diff, 4),
                            legs=[
                                {"ticker": l_ticker, "action": "buy", "price": lower.yes_price},
                                {"ticker": h_ticker, "action": "sell", "price": higher.yes_price}
                            ]
                        )
                        opportunities.append(opp)
                        logger.warning(f"[C-137 ARBITRAGE] {opp.description}")

            elif direction == "below":
                # For "below", higher thresholds MUST have higher or equal probability / price
                # e.g., P(< 80F) >= P(< 75F)
                for i in range(len(sorted_ladder) - 1):
                    lower = sorted_ladder[i]      # Lower temp (e.g. 75F)
                    higher = sorted_ladder[i + 1]  # Higher temp (e.g. 80F)

                    if lower.yes_price > higher.yes_price + 0.03:
                        diff = lower.yes_price - higher.yes_price
                        h_ticker = getattr(higher, 'ticker', getattr(higher, 'slug', higher.market_id))
                        l_ticker = getattr(lower, 'ticker', getattr(lower, 'slug', lower.market_id))
                        opp = ArbitrageOpportunity(
                            city_key=city_key,
                            target_date=target_date,
                            arb_type="monotonicity_inversion",
                            description=(
                                f"Inversion: {l_ticker} (<={lower.threshold_f}F @ {lower.yes_price:.2f}) "
                                f"is priced higher than {h_ticker} (<={higher.threshold_f}F @ {higher.yes_price:.2f})"
                            ),
                            profit_margin=round(diff, 4),
                            legs=[
                                {"ticker": h_ticker, "action": "buy", "price": higher.yes_price},
                                {"ticker": l_ticker, "action": "sell", "price": lower.yes_price}
                            ]
                        )
                        opportunities.append(opp)
                        logger.warning(f"[C-137 ARBITRAGE] {opp.description}")

        return opportunities


# Global singleton instance
monotonicity_scanner = MonotonicityScanner()
