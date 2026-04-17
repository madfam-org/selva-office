"""selva-doctor — preflight check for the Selva/Selva runtime.

Absorbed from the claw-code ``/doctor`` surface as a capability; our
implementation is original. Verifies that every operational dependency a
Selva task may touch is present, authenticated, and reachable — before
the agent starts spending tokens.

Usage::

    from selva_doctor import Doctor, Check, CheckStatus
    doctor = Doctor()
    report = await doctor.run()
    if not report.ok:
        print(report.to_text())
        raise SystemExit(1)
"""

from .checks import (
    Check,
    CheckStatus,
    DoctorReport,
    default_checks,
)
from .doctor import Doctor

__all__ = [
    "Check",
    "CheckStatus",
    "Doctor",
    "DoctorReport",
    "default_checks",
]

__version__ = "0.1.0"
