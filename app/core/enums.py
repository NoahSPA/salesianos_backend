from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    admin = "admin"
    delegado = "delegado"
    tesorero = "tesorero"
    jugador = "jugador"


class MatchStatus(str, Enum):
    programado = "programado"
    borrador = "borrador"
    publicado = "publicado"
    jugado = "jugado"
    suspendido = "suspendido"
    reprogramado = "reprogramado"


class AttendanceStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    declined = "declined"


class PaymentStatus(str, Enum):
    pending_validation = "pending_validation"
    confirmed = "confirmed"  # validated by treasurer
    validated = "validated"  # legacy, mismo que confirmed
    rejected = "rejected"
    reversed = "reversed"  # cancelled payment


class FeeStatus(str, Enum):
    al_dia = "al_dia"
    pendiente = "pendiente"
    atrasado = "atrasado"


class PlayerPosition(str, Enum):
    # Portero
    gk = "gk"
    # Defensa
    rb = "rb"    # lateral derecho
    cb = "cb"    # central
    lb = "lb"    # lateral izquierdo
    rwb = "rwb"  # carrilero derecho
    lwb = "lwb"  # carrilero izquierdo
    # Medio
    dm = "dm"    # medio defensivo
    cm = "cm"    # medio centro
    am = "am"    # medio ofensivo
    # Ataque
    rw = "rw"    # extremo derecho
    lw = "lw"    # extremo izquierdo
    st = "st"    # delantero centro
    cf = "cf"    # segundo delantero / falso 9

