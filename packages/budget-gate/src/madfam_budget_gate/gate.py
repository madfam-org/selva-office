"""HITL budget gate for Meta-Harness runs.

Design goals:
    1. Nothing spends tokens before a human types an approval challenge.
    2. The challenge is specific to this run (not a habitual "yes").
    3. An approval is a durable audit record, not a terminal scrollback line.
    4. Mid-run spend is tracked against the approved cap; breach => hard kill.

The gate is intentionally small. It does NOT try to be a full policy engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from .cost_model import CostEstimate


class BudgetDenied(RuntimeError):
    """Raised when the gate refuses (user rejection, cap breach, bad config)."""


class BudgetExceededError(BudgetDenied):
    """Raised mid-run when actual spend breaches the approved cap."""


@dataclass(frozen=True)
class GateConfig:
    hard_cap_usd: float
    grace_factor: float
    approvals_dir: Path
    logs_dir: Path
    experiment_id: str
    experiment_owner: str

    @classmethod
    def from_env(cls) -> "GateConfig":
        hard_cap = float(os.environ.get("MADFAM_BUDGET_HARD_CAP_USD", "0") or 0)
        if hard_cap <= 0:
            raise BudgetDenied(
                "MADFAM_BUDGET_HARD_CAP_USD is not set (or is 0). Refusing to run. "
                "Set it to the maximum USD you are willing to spend in this session."
            )
        grace = float(os.environ.get("MADFAM_BUDGET_GRACE_FACTOR", "1.10"))
        if grace < 1.0 or grace > 2.0:
            raise BudgetDenied(
                f"MADFAM_BUDGET_GRACE_FACTOR={grace} out of range [1.0, 2.0]."
            )
        exp_id = os.environ.get("MADFAM_EXPERIMENT_ID", "").strip()
        if not exp_id:
            raise BudgetDenied("MADFAM_EXPERIMENT_ID must be set.")
        owner = os.environ.get("MADFAM_EXPERIMENT_OWNER", "").strip()
        if not owner:
            raise BudgetDenied(
                "MADFAM_EXPERIMENT_OWNER must be set — who is approving this spend?"
            )
        approvals_dir = Path(os.environ.get("MADFAM_APPROVALS_DIR", "./approvals"))
        logs_dir = Path(os.environ.get("MADFAM_LOGS_DIR", "./logs"))
        approvals_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            hard_cap_usd=hard_cap,
            grace_factor=grace,
            approvals_dir=approvals_dir,
            logs_dir=logs_dir,
            experiment_id=exp_id,
            experiment_owner=owner,
        )


def _challenge_string(estimate: CostEstimate, experiment_id: str) -> str:
    """Deterministic challenge string the approver must type verbatim.

    It folds in the estimated cost so that if the estimate changes the
    challenge changes — an approver can't copy-paste a stale approval.
    """
    payload = (
        f"{experiment_id}|{estimate.run.model}|{estimate.run.iterations}|"
        f"{estimate.run.candidates_per_iteration}|{estimate.run.eval_set_size}|"
        f"{estimate.total_usd:.4f}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    amount = f"{estimate.total_usd:.2f}".replace(".", "p")
    return f"approve-{experiment_id}-{amount}usd-{digest}"


@dataclass
class ApprovalRecord:
    experiment_id: str
    experiment_owner: str
    approved_at: str
    approved_cap_usd: float
    grace_factor: float
    hard_kill_at_usd: float
    estimate: dict
    challenge: str
    tty: str

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)


def require_approval(
    estimate: CostEstimate,
    cfg: GateConfig,
    *,
    input_stream: IO[str] | None = None,
    output_stream: IO[str] | None = None,
) -> ApprovalRecord:
    """Block until the user types the challenge string verbatim.

    - If the estimate exceeds the hard cap, refuse outright.
    - Otherwise print a summary and the challenge, and read stdin.
    - On success, write an approval record to ``cfg.approvals_dir``.
    """
    inp = input_stream if input_stream is not None else sys.stdin
    out = output_stream if output_stream is not None else sys.stdout

    if estimate.total_usd > cfg.hard_cap_usd:
        raise BudgetDenied(
            f"Estimated cost ${estimate.total_usd:.2f} exceeds hard cap "
            f"${cfg.hard_cap_usd:.2f}. Raise MADFAM_BUDGET_HARD_CAP_USD "
            "deliberately and re-run if you truly want this."
        )

    challenge = _challenge_string(estimate, cfg.experiment_id)
    kill_at = estimate.total_usd * cfg.grace_factor

    out.write("\n=== META-HARNESS BUDGET GATE ===\n")
    out.write(f"experiment       : {cfg.experiment_id}\n")
    out.write(f"owner            : {cfg.experiment_owner}\n")
    for line in estimate.summary_lines():
        out.write(f"{line}\n")
    out.write(f"hard cap (env)   : ${cfg.hard_cap_usd:,.2f}\n")
    out.write(
        f"mid-run kill at  : ${kill_at:,.2f} "
        f"({cfg.grace_factor:.2f}x approved cost)\n"
    )
    out.write("\nTo approve, type the following challenge verbatim:\n")
    out.write(f"  {challenge}\n")
    out.write("Anything else will cancel.\n> ")
    out.flush()

    typed = inp.readline().strip()
    if typed != challenge:
        raise BudgetDenied("Approval challenge did not match. Run cancelled.")

    record = ApprovalRecord(
        experiment_id=cfg.experiment_id,
        experiment_owner=cfg.experiment_owner,
        approved_at=datetime.now(timezone.utc).isoformat(),
        approved_cap_usd=estimate.total_usd,
        grace_factor=cfg.grace_factor,
        hard_kill_at_usd=kill_at,
        estimate={
            "model": estimate.run.model,
            "iterations": estimate.run.iterations,
            "candidates_per_iteration": estimate.run.candidates_per_iteration,
            "eval_set_size": estimate.run.eval_set_size,
            "input_tokens_per_eval": estimate.run.input_tokens_per_eval,
            "output_tokens_per_eval": estimate.run.output_tokens_per_eval,
            "proposer_model": estimate.run.proposer_model,
            "total_usd": estimate.total_usd,
            "inner_loop_usd": estimate.inner_loop_usd,
            "proposer_usd": estimate.proposer_usd,
            "total_input_tokens": estimate.total_input_tokens,
            "total_output_tokens": estimate.total_output_tokens,
        },
        challenge=challenge,
        tty=os.environ.get("TTY") or os.ttyname(0) if sys.stdin.isatty() else "non-tty",
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(challenge.encode()).hexdigest()[:8]
    target = cfg.approvals_dir / f"{ts}_{cfg.experiment_id}_{digest}.json"
    target.write_text(record.to_json())
    out.write(f"\nApproval recorded: {target}\n")
    out.flush()
    return record


@dataclass
class SpendTracker:
    """Mid-run spend accumulator. Trips a hard kill if the cap is breached.

    The tracker is append-only and thread-safe. Call ``record_usage`` after
    every LLM call. The background watcher checks the total against the
    approved kill threshold and, if breached, raises ``BudgetExceededError``
    from the main thread (and logs the breach).

    The watcher deliberately does NOT try to refund anything. It also does not
    try to cancel in-flight requests — cost has already been incurred by the
    provider at that point. The goal is to stop the NEXT call, not the
    current one.
    """

    approved_cap_usd: float
    kill_at_usd: float
    log_path: Path
    _total_usd: float = 0.0
    _total_input_tokens: int = 0
    _total_output_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _killed: bool = False

    @property
    def total_usd(self) -> float:
        with self._lock:
            return self._total_usd

    def assert_not_killed(self) -> None:
        if self._killed:
            raise BudgetExceededError(
                f"Run was killed because spend ${self._total_usd:.2f} "
                f"exceeded ${self.kill_at_usd:.2f} (approved cap "
                f"${self.approved_cap_usd:.2f})."
            )

    def record_usage(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        usd: float,
        tag: str | None = None,
    ) -> None:
        """Record a completed LLM call. Raises if cap already breached."""
        self.assert_not_killed()
        with self._lock:
            self._total_usd += usd
            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens
            over_cap = self._total_usd > self.kill_at_usd
        with self.log_path.open("a") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "model": model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "usd": round(usd, 6),
                        "running_total_usd": round(self._total_usd, 6),
                        "tag": tag,
                    }
                )
                + "\n"
            )
        if over_cap:
            self._killed = True
            # Proactively signal the main thread so the next iteration bails.
            try:
                os.kill(os.getpid(), signal.SIGUSR1)
            except (OSError, AttributeError):
                # Windows or restricted env — the next assert_not_killed will
                # still catch it.
                pass
            raise BudgetExceededError(
                f"Spend ${self._total_usd:.2f} exceeded ${self.kill_at_usd:.2f}."
            )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total_usd": round(self._total_usd, 6),
                "total_input_tokens": self._total_input_tokens,
                "total_output_tokens": self._total_output_tokens,
                "approved_cap_usd": self.approved_cap_usd,
                "kill_at_usd": self.kill_at_usd,
                "killed": self._killed,
            }


def install_sigusr1_tripwire(tracker: SpendTracker) -> None:
    """Promote a SIGUSR1 from the worker thread into a BudgetExceededError.

    Only available on POSIX. Silently no-ops otherwise.
    """
    if not hasattr(signal, "SIGUSR1"):
        return

    def _handler(_signum: int, _frame) -> None:
        # Raising from a signal handler is allowed in CPython main thread.
        tracker.assert_not_killed()

    try:
        signal.signal(signal.SIGUSR1, _handler)
    except (ValueError, OSError):
        # Not in main thread, or restricted — the tracker.assert_not_killed
        # polling path still works.
        pass


def new_tracker(approved: ApprovalRecord, cfg: GateConfig) -> SpendTracker:
    log_path = cfg.logs_dir / f"spend_{int(time.time())}_{cfg.experiment_id}.jsonl"
    # Default SIGUSR1 to ignore so the signal we send on cap breach doesn't
    # terminate the process before `assert_not_killed` gets a chance to run
    # (SIGUSR1's default action is to kill). `install_sigusr1_tripwire` can
    # later replace this with a raising handler if the caller wants one.
    if hasattr(signal, "SIGUSR1"):
        try:
            signal.signal(signal.SIGUSR1, signal.SIG_IGN)
        except (ValueError, OSError):
            pass
    return SpendTracker(
        approved_cap_usd=approved.approved_cap_usd,
        kill_at_usd=approved.hard_kill_at_usd,
        log_path=log_path,
    )
