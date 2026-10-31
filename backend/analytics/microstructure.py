"""
=============================================================================
C-137 QUANTITATIVE MICROSTRUCTURE & CORRECTION ENGINE
Transplanted from: OMNI-KALSHI-C137 (delightful-bose)
Inspired by: Jon Becker (prediction-market-analysis)
Author: Rick Sanchez (Dimension C-137)
Purpose: Replaces retail candle voodoo (RSI/SMA) with mathematical order book
         microstructure. Applies Favorite-Longshot Bias (FLB) warping and
         friction-adjusted net edge hurdles.
=============================================================================
"""

import math
from typing import Optional, Tuple, List


class MicrostructureEngine:
    """
    Jon Becker Microstructure Quant Core.
    Converts raw, dirty market prices into mathematically sound true probabilities.
    """

    def __init__(self, flb_alpha: float = 0.88, taker_fee_pct: float = 0.015):
        self.flb_alpha = flb_alpha
        self.taker_fee_pct = taker_fee_pct

    def calibrate_probability(self, raw_market_prob: float) -> float:
        """
        Applies empirical Favorite-Longshot Bias (FLB) correction curve.
        Retail chimps systematically overpay for 5-cent contracts hoping for a 20x miracle.
        This function quantifies that bias and extracts the true underlying probability.

        Longshots (p < 0.5): true probability is strictly LOWER than retail ask.
        Favorites (p > 0.5): true probability is strictly HIGHER than retail bid.
        """
        p = max(0.001, min(0.999, raw_market_prob))

        # Power-law probability warping
        # Continuous Becker Power-Law Favorite-Longshot Bias (FLB) warping
        # Smoothly dampens longshot bias while rewarding high-probability favorites
        gamma = 1.15
        p_g = p ** gamma
        calibrated_p = p_g / (p_g + ((1.0 - p) ** gamma))

        return max(0.001, min(0.999, calibrated_p))

    def compute_order_book_imbalance(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        depth_levels: int = 3
    ) -> float:
        """
        Computes normalized Order Book Imbalance (OBI) in range [-1.0, 1.0].
        bids and asks are lists of (price, size).
        Positive values indicate strong buying pressure on YES.
        Negative values indicate sell pressure / flight to NO.
        """
        bid_vol = sum(size for _, size in bids[:depth_levels])
        ask_vol = sum(size for _, size in asks[:depth_levels])

        total_vol = bid_vol + ask_vol
        if total_vol <= 0:
            return 0.0

        return (bid_vol - ask_vol) / float(total_vol)

    def calculate_effective_friction(
        self,
        price: float,
        contracts: float = 10.0,
        is_taker: bool = True
    ) -> float:
        """
        Calculates total transaction friction in probability space (exchange fee + slippage allowance).
        Taker fee ~1.5% + volume impact slippage.
        """
        fee = price * (self.taker_fee_pct if is_taker else 0.0)
        # Volume impact: 0.001 (0.1c) per 50 contracts
        slippage = (contracts / 50.0) * 0.001
        return fee + slippage

    def extract_net_edge(
        self,
        model_prob: float,
        market_price: float,
        contracts: float = 10.0,
        min_hurdle: float = 0.03
    ) -> Tuple[bool, float, float]:
        """
        Compares calibrated model probability against execution price after friction.
        Returns: (has_positive_edge, net_edge, execution_price)
        """
        calibrated_prob = self.calibrate_probability(model_prob)
        friction = self.calculate_effective_friction(market_price, contracts)
        net_edge = calibrated_prob - market_price - friction

        has_edge = net_edge >= min_hurdle
        return has_edge, net_edge, market_price
