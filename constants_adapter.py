# -*- coding: utf-8 -*-
"""
constants_adapter.py — ekspordib pricing_engine.py jaoks vajalikud konstandid config.json põhjal.

pricing_engine.py impordib siit:
    WELDING_HOURLY_RATE, WELDING_SPEEDS, CLEANING_HOURLY_RATE, CLEANING_SPEED,
    OP_HOURLY_RATE, MATERIAL_PROPERTIES, CUTTING_SPEEDS
"""
from __future__ import annotations

from config_manager import cfg

# Tunnimäärad
OP_HOURLY_RATE: float = float(cfg.get("rates", "operator_hourly", default=80.0))
WELDING_HOURLY_RATE: float = float(cfg.get("rates", "welding_hourly", default=40.0))
CLEANING_HOURLY_RATE: float = float(cfg.get("rates", "cleaning_hourly", default=40.0))

# Keevituskiirused mm/min (MIG/MAG ja TIG)
WELDING_SPEEDS: dict[str, float] = {
    "MIG/MAG": 120.0,
    "TIG": 70.0,
}

# Puhastuskiirus mm/min
CLEANING_SPEED: float = 250.0

# Materjalide omadused — loetakse config.json "materials" sektsioonist
MATERIAL_PROPERTIES: dict[str, dict] = cfg.get("materials", default={})

# Lõikekiirused mm/min — loetakse config.json "cutting_speeds_mm_min" sektsioonist
# Võtmed teisendatakse float-ideks, et paksuse valik toimiks korrektselt
_raw_speeds: dict[str, dict] = cfg.get("cutting_speeds_mm_min", default={})
CUTTING_SPEEDS: dict[str, dict[float, float]] = {
    mat: {float(th): float(spd) for th, spd in speeds.items()}
    for mat, speeds in _raw_speeds.items()
}
