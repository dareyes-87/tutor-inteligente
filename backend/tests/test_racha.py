"""racha_vigente: la racha mostrada caduca si la última actividad es anterior a ayer (hora de Guatemala)."""
from datetime import date
from types import SimpleNamespace

from freezegun import freeze_time

from app.modules.lecciones.service import racha_vigente


def _u(ultima):
    return SimpleNamespace(racha_actual=5, mejor_racha=7, ultima_actividad=ultima)


@freeze_time("2026-11-07 18:00:00")  # 12:00 en Guatemala
def test_racha_caduca_y_se_mantiene():
    assert racha_vigente(_u(date(2026, 11, 5))) == 0   # hace 2 días
    assert racha_vigente(_u(date(2026, 11, 6))) == 5   # ayer
    assert racha_vigente(_u(date(2026, 11, 7))) == 5   # hoy
    assert racha_vigente(_u(None)) == 0


@freeze_time("2026-11-08 03:00:00")  # 21:00 del 7 en Guatemala: aún es el 7 allí
def test_usa_el_dia_de_guatemala_no_el_de_utc():
    assert racha_vigente(_u(date(2026, 11, 6))) == 5
