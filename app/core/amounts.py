"""
Montos en unidades de mil (miles de CLP).
15 = 15.000 CLP
"""


def thousands_to_clp(thousands: int) -> int:
    """Unidades de mil → CLP. 15 → 15000."""
    return thousands * 1000


def clp_to_thousands(clp: int) -> int:
    """CLP → unidades de mil. 15000 → 15."""
    return max(0, clp // 1000)
