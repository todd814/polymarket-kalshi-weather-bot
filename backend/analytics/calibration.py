"""
=============================================================================
C-137 SETTLEMENT CALIBRATION & NEGATIVE-EDGE LOCKDOWN HARNESS
Transplanted from: OMNI-KALSHI-C137 (delightful-bose)
Inspired by: Ryan Frigo (kalshi-ai-trading-bot)
Author: Rick Sanchez (Dimension C-137)
Purpose: Computes rolling Brier Scores and Log-Loss on real cash settlements.
         Automatically triggers an instant category kill-switch if Brier > 0.245
         (meaning the model is performing worse than a random coin flip).
=============================================================================
"""

import dataclasses
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple


@dataclass
class SettlementRecord:
    trade_id: str
    ticker: str
    category: str
    predicted_prob: float
    actual_outcome: float       # 1.0 for WIN, 0.0 for LOSS
    brier_contribution: float
    log_loss_contribution: float
    size: float
    entry_price: float
    pnl: float
    settled_at: float = field(default_factory=time.time)


class SettlementCalibrationHarness:
    """
    Ryan Frigo Calibration & Negative Edge Kill Switch.
    Maintains persistent audit ledger of model calibration against true settlements.
    """

    def __init__(
        self,
        journal_path: str = "trade_journal.jsonl",
        brier_threshold: float = 0.245,
        min_trades_for_audit: int = 3
    ):
        self.journal_path = journal_path
        self.brier_threshold = brier_threshold
        self.min_trades_for_audit = min_trades_for_audit
        self.settled_records: List[SettlementRecord] = []
        self.category_records: Dict[str, List[SettlementRecord]] = {
            "btc": [],
            "weather": [],
            "general": []
        }
        self.locked_categories: Dict[str, str] = {}
        self._load_journal()

    def _load_journal(self) -> None:
        """Loads historical settled trades from journal if present."""
        if not os.path.exists(self.journal_path):
            return

        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    rec = SettlementRecord(
                        trade_id=str(data["trade_id"]),
                        ticker=data["ticker"],
                        category=data.get("category", "general"),
                        predicted_prob=float(data["predicted_prob"]),
                        actual_outcome=float(data["actual_outcome"]),
                        brier_contribution=float(data["brier_contribution"]),
                        log_loss_contribution=float(data["log_loss_contribution"]),
                        size=float(data.get("size", 0.0)),
                        entry_price=float(data.get("entry_price", 0.0)),
                        pnl=float(data.get("pnl", 0.0)),
                        settled_at=float(data.get("settled_at", time.time()))
                    )
                    self.settled_records.append(rec)
                    if rec.category not in self.category_records:
                        self.category_records[rec.category] = []
                    self.category_records[rec.category].append(rec)

            self.evaluate_category_lockdowns()
        except Exception as e:
            print(f"[C-137] Warning: Failed to parse trade journal {self.journal_path}: {e}")

    def record_settlement(
        self,
        trade_id: str,
        ticker: str,
        category: str,
        predicted_prob: float,
        actual_outcome: float,  # 1.0 for WIN, 0.0 for LOSS
        size: float,
        entry_price: float,
        pnl: float
    ) -> SettlementRecord:
        """
        Records a newly settled trade, computes Brier contribution and log-loss,
        appends to journal, and evaluates lockdown trigger.
        """
        # Brier score contribution: (prob - outcome)^2
        # Perfectly calibrated prediction = 0.0, random coin-flip = 0.25, completely inverted = 1.0
        brier = (predicted_prob - actual_outcome) ** 2

        # Log-loss: - [y * log(p) + (1-y) * log(1-p)]
        eps = 1e-6
        clamped_p = max(eps, min(1.0 - eps, predicted_prob))
        log_loss = -(
            actual_outcome * math.log(clamped_p) +
            (1.0 - actual_outcome) * math.log(1.0 - clamped_p)
        )

        record = SettlementRecord(
            trade_id=trade_id,
            ticker=ticker,
            category=category,
            predicted_prob=predicted_prob,
            actual_outcome=actual_outcome,
            brier_contribution=brier,
            log_loss_contribution=log_loss,
            size=size,
            entry_price=entry_price,
            pnl=pnl,
            settled_at=time.time()
        )

        self.settled_records.append(record)
        if category not in self.category_records:
            self.category_records[category] = []
        self.category_records[category].append(record)

        # Append to journal file immediately
        try:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(dataclasses.asdict(record)) + "\n")
        except Exception as e:
            print(f"[C-137] Warning: Failed to write to {self.journal_path}: {e}")

        self.evaluate_category_lockdowns()
        return record

    def get_category_brier(self, category: str) -> Optional[float]:
        """Calculates current mean Brier score for a specific category."""
        records = self.category_records.get(category, [])
        if not records:
            return None
        return sum(r.brier_contribution for r in records) / len(records)

    def get_global_brier(self) -> Optional[float]:
        """Calculates overall Brier score across all settled markets."""
        if not self.settled_records:
            return None
        return sum(r.brier_contribution for r in self.settled_records) / len(self.settled_records)

    def evaluate_category_lockdowns(self) -> None:
        """
        Frigo Kill Switch: If category Brier score > threshold AND cumulative P&L < 0
        with sufficient sample size, lock it down instantly.
        Never lock down a net-profitable category.
        """
        for cat, recs in self.category_records.items():
            if len(recs) >= self.min_trades_for_audit:
                mean_brier = sum(r.brier_contribution for r in recs) / len(recs)
                total_pnl = sum(r.pnl for r in recs)
                if mean_brier > self.brier_threshold and total_pnl < 0:
                    self.locked_categories[cat] = (
                        f"NEGATIVE EDGE LOCKDOWN: Brier score {mean_brier:.4f} > limit {self.brier_threshold:.4f} "
                        f"and P&L ${total_pnl:.2f} < $0 across {len(recs)} trades. Model is hallucinating."
                    )
                elif cat in self.locked_categories and (mean_brier <= self.brier_threshold or total_pnl >= 0):
                    del self.locked_categories[cat]

    def is_category_permitted(self, category: str) -> Tuple[bool, Optional[str]]:
        """Checks if category is cleared for live execution."""
        if category in self.locked_categories:
            return False, self.locked_categories[category]
        return True, None


# Global singleton instance (requires 20+ live settled trades before auditing)
calibration_harness = SettlementCalibrationHarness(min_trades_for_audit=20)
