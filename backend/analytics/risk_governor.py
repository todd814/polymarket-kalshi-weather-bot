"""
=============================================================================
C-137 5-GATE FORTRESS RISK GOVERNOR
Transplanted from: OMNI-KALSHI-C137 (delightful-bose)
Inspired by: OctagonAI (kalshi-trading-bot-cli)
Author: Rick Sanchez (Dimension C-137)
Purpose: The 5-gate defense system. Every proposed trade must survive all five
         gates or it gets vaporized before reaching order placement.
=============================================================================
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from backend.analytics.calibration import calibration_harness


@dataclass
class GateResult:
    passed: bool
    approved_size: float
    rejection_reason: Optional[str] = None
    gate_failed: Optional[int] = None


class OmniRiskGovernor:
    """
    OctagonAI 5-Gate Fortress Risk Architecture:
      Gate 1: Liquidity & Spread Gate (spread <= 0.08, not illiquid)
      Gate 2: Minimum Net Edge Hurdle Gate (edge after friction >= 0.03)
      Gate 3: Fractional Kelly Position Sizing Gate (Quarter-Kelly)
      Gate 4: Sector Correlation & Concentration Gate (category <= 35% bankroll)
      Gate 5: High-Water Mark Drawdown Circuit Breaker Gate (drawdown < 15%)
    """

    def __init__(
        self,
        max_spread: float = 0.08,
        min_net_edge: float = 0.03,
        max_drawdown_pct: float = 0.15,
        max_category_exposure_pct: float = 0.35,
        kelly_fraction: float = 0.25
    ):
        self.max_spread = max_spread
        self.min_net_edge = min_net_edge
        self.max_drawdown_pct = max_drawdown_pct
        self.max_category_exposure_pct = max_category_exposure_pct
        self.kelly_fraction = kelly_fraction

    def evaluate_order(
        self,
        category: str,
        entry_price: float,
        model_prob: float,
        net_edge: float,
        spread: float,
        current_bankroll: float,
        category_exposure: float,
        high_water_mark: float
    ) -> GateResult:
        """
        Runs signal sequentially through the 5 gates.
        """
        # --- Pre-Flight: Frigo Calibration Check ---
        is_cleared, reason = calibration_harness.is_category_permitted(category)
        if not is_cleared:
            return GateResult(
                passed=False,
                approved_size=0.0,
                rejection_reason=f"PRE-FLIGHT REJECTED: {reason}",
                gate_failed=0
            )

        # --- Gate 5: Drawdown Circuit Breaker ---
        if high_water_mark > 0:
            drawdown = (high_water_mark - current_bankroll) / high_water_mark
            if drawdown >= self.max_drawdown_pct:
                return GateResult(
                    passed=False,
                    approved_size=0.0,
                    rejection_reason=f"GATE 5 REJECTED: Drawdown {drawdown:.1%} exceeds max {self.max_drawdown_pct:.1%}",
                    gate_failed=5
                )

        # --- Gate 1: Spread / Liquidity Check ---
        if spread > self.max_spread:
            return GateResult(
                passed=False,
                approved_size=0.0,
                rejection_reason=f"GATE 1 REJECTED: Bid-ask spread {spread:.1%} exceeds max allowed {self.max_spread:.1%}",
                gate_failed=1
            )

        # --- Gate 2: Net Edge Hurdle ---
        if net_edge < self.min_net_edge:
            return GateResult(
                passed=False,
                approved_size=0.0,
                rejection_reason=f"GATE 2 REJECTED: Net edge {net_edge:.2%} below hurdle {self.min_net_edge:.2%}",
                gate_failed=2
            )

        # --- Gate 3: Quarter-Kelly Sizing ---
        if entry_price <= 0.01 or entry_price >= 0.99 or model_prob <= entry_price:
            return GateResult(
                passed=False,
                approved_size=0.0,
                rejection_reason="GATE 3 REJECTED: Negative expectation (model_prob <= entry_price)",
                gate_failed=3
            )

        # Full Kelly f* = (p - price) / (1 - price)
        kelly_full = (model_prob - entry_price) / (1.0 - entry_price)
        kelly_fractional = max(0.0, kelly_full * self.kelly_fraction)
        suggested_size = min(kelly_fractional * current_bankroll, current_bankroll * 0.05)

        if suggested_size < 1.0:
            return GateResult(
                passed=False,
                approved_size=0.0,
                rejection_reason=f"GATE 3 REJECTED: Kelly size ${suggested_size:.2f} below $1.00 minimum",
                gate_failed=3
            )

        # --- Gate 4: Category Exposure Cap ---
        max_allowed_category = current_bankroll * self.max_category_exposure_pct
        if category_exposure + suggested_size > max_allowed_category:
            remaining_cap = max(0.0, max_allowed_category - category_exposure)
            if remaining_cap < 1.0:
                return GateResult(
                    passed=False,
                    approved_size=0.0,
                    rejection_reason=f"GATE 4 REJECTED: Category '{category}' cap reached (${category_exposure:.2f}/${max_allowed_category:.2f})",
                    gate_failed=4
                )
            suggested_size = remaining_cap

        return GateResult(
            passed=True,
            approved_size=round(suggested_size, 2)
        )


# Global singleton instance
omni_risk_governor = OmniRiskGovernor()
