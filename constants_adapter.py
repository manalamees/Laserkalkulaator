"""
constants_adapter.py
--------------------
Ühilduvuskiht sinu olemasolevale koodile.
Loeb väärtused ConfigManager'ist ja peegeldab need samade nimedena,
mida vana kood eeldab (LASER_HOURLY_RATE, MATERIAL_PROPERTIES, CUTTING_SPEEDS, ...).

NB! Kui muudate seadeid SettingsDialogis, kutsu pärast salvestust:
    import constants_adapter
    constants_adapter.refresh()
siis uuenevad ka siin eksporditavad globaalsed väärtused.
"""
from __future__ import annotations

from typing import Dict, Any
from config_manager import cfg

# --------- sisemine teisendus abi ---------
def _build_material_properties() -> Dict[str, Dict[str, Any]]:
    mats = cfg.get("materials", default={})
    return {
        k: {
            "label": v.get("label", k),
            "density_kg_m3": float(v.get("density_kg_m3", 0.0) or 0.0),
            "price_eur_kg": float(v.get("price_eur_kg", 0.0) or 0.0),
        }
        for k, v in mats.items()
    }


def _build_cutting_speeds() -> Dict[str, Dict[float, float]]:
    raw = cfg.get("cutting_speeds_mm_min", default={})
    table: Dict[str, Dict[float, float]] = {}
    for mat, mapping in (raw or {}).items():
        inner: Dict[float, float] = {}
        for thk_str, spd in (mapping or {}).items():
            try:
                thk = float(thk_str)
            except Exception:
                # ignore malformed keys
                continue
            try:
                inner[thk] = float(spd)
            except Exception:
                inner[thk] = 0.0
        # sort keys by thickness (not necessary for dict, but nice to keep tidy)
        table[mat] = dict(sorted(inner.items(), key=lambda kv: kv[0]))
    return table


def _build_welding_speeds() -> Dict[str, float]:
    raw = cfg.get("speeds", "welding_mm_min", default={})
    return {str(k): float(v) for k, v in (raw or {}).items()}


def _rate(path1: str, path2: str) -> float:
    try:
        return float(cfg.get(path1, path2, default=0.0))
    except Exception:
        return 0.0


def _cleaning_speed() -> float:
    try:
        return float(cfg.get("speeds", "cleaning_mm_min", default=0.0))
    except Exception:
        return 0.0


# --------- avalikud “konstandid” + refresh() ---------
LASER_HOURLY_RATE: float = _rate("rates", "laser_hourly")
WELDING_HOURLY_RATE: float = _rate("rates", "welding_hourly")
CLEANING_HOURLY_RATE: float = _rate("rates", "cleaning_hourly")
OP_HOURLY_RATE: float = _rate("rates", "operator_hourly")

WELDING_SPEEDS: Dict[str, float] = _build_welding_speeds()
CLEANING_SPEED: float = _cleaning_speed()

MATERIAL_PROPERTIES: Dict[str, Dict[str, Any]] = _build_material_properties()
CUTTING_SPEEDS: Dict[str, Dict[float, float]] = _build_cutting_speeds()


def refresh() -> None:
    """
    Uuenda kõik väärtused praeguse config.json sisu põhjal.
    Kutsu seda pärast SettingsDialog -> Salvesta.
    """
    global LASER_HOURLY_RATE, WELDING_HOURLY_RATE, CLEANING_HOURLY_RATE, OP_HOURLY_RATE
    global WELDING_SPEEDS, CLEANING_SPEED, MATERIAL_PROPERTIES, CUTTING_SPEEDS

    LASER_HOURLY_RATE = _rate("rates", "laser_hourly")
    WELDING_HOURLY_RATE = _rate("rates", "welding_hourly")
    CLEANING_HOURLY_RATE = _rate("rates", "cleaning_hourly")
    OP_HOURLY_RATE = _rate("rates", "operator_hourly")

    WELDING_SPEEDS = _build_welding_speeds()
    CLEANING_SPEED = _cleaning_speed()

    MATERIAL_PROPERTIES = _build_material_properties()
    CUTTING_SPEEDS = _build_cutting_speeds()
