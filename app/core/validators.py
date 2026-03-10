from __future__ import annotations

import re


_RUT_RE = re.compile(r"^\s*([0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3})-?([0-9kK])\s*$")


def normalize_rut(value: str) -> str:
    """
    Normaliza a formato '12345678-9' (sin puntos, DV en mayúscula).
    """
    m = _RUT_RE.match(value or "")
    if not m:
        raise ValueError("RUT inválido")
    num = re.sub(r"\D", "", m.group(1))
    dv = m.group(2).upper()
    if not (7 <= len(num) <= 8):
        raise ValueError("RUT inválido")
    rut = f"{int(num)}-{dv}"
    if not validate_rut(rut):
        raise ValueError("RUT inválido")
    return rut


def validate_rut(value: str) -> bool:
    m = _RUT_RE.match(value or "")
    if not m:
        return False
    num = re.sub(r"\D", "", m.group(1))
    dv = m.group(2).upper()
    try:
        n = int(num)
    except ValueError:
        return False

    s = 0
    mul = 2
    while n > 0:
        s += (n % 10) * mul
        n //= 10
        mul = 2 if mul == 7 else mul + 1
    r = 11 - (s % 11)
    expected = "0" if r == 11 else "K" if r == 10 else str(r)
    return expected == dv

