# -*- coding: utf-8 -*-
"""
DXF laserlõikuse hinnakalkulaatori arvutusmootor veebiversioonile.

See fail on teadlikult ilma PyQt5 sõltuvuseta, et sama loogikat saaks kasutada
Streamlit/FastAPI/React veebirakenduses.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Tuple
from collections import namedtuple

import ezdxf

Pt = namedtuple("Pt", ["x", "y", "bulge"])


# -----------------------------------------------------------------------------
# SEADISTUSED
#
# Veebiversioon proovib nüüd kasutada sinu vana programmi andmefaile:
#   - constants_adapter.py  -> materjalid, paksused, kiirused, tunnihinnad
#   - config_manager.py     -> cfg.get(...) seaded, kui fail on olemas
#
# Kui neid faile kõrval ei ole, kasutatakse allolevaid varu-/näidisandmeid.
# -----------------------------------------------------------------------------
CONFIG_SOURCE = "fallback_demo_values"

class _FallbackCfg:
    def get(self, section: str, key: str, default=None):
        return default

try:
    from config_manager import cfg  # sinu vana programmi cfg
    _HAS_OLD_CFG = True
except Exception:
    cfg = _FallbackCfg()
    _HAS_OLD_CFG = False

_FALLBACK_OP_HOURLY_RATE = 45.0
_FALLBACK_WELDING_HOURLY_RATE = 55.0
_FALLBACK_CLEANING_HOURLY_RATE = 35.0
_FALLBACK_CLEANING_SPEED = 250.0
_FALLBACK_WELDING_SPEEDS: Dict[str, float] = {
    "MIG/MAG": 120.0,
    "TIG": 70.0,
}
_FALLBACK_MATERIAL_PROPERTIES: Dict[str, Dict[str, Any]] = {
    "CS": {"label": "Must teras", "density_kg_m3": 7850, "price_eur_kg": 1.50},
    "ZN": {"label": "Tsingitud teras", "density_kg_m3": 7850, "price_eur_kg": 1.80},
    "RST304": {"label": "Roostevaba teras AISI 304", "density_kg_m3": 8000, "price_eur_kg": 4.20},
    "AL": {"label": "Alumiinium", "density_kg_m3": 2700, "price_eur_kg": 4.00},
}
_FALLBACK_CUTTING_SPEEDS: Dict[str, Dict[float, float]] = {
    "CS": {1.0: 4200, 1.5: 3500, 2.0: 2800, 3.0: 2100, 4.0: 1600, 5.0: 1200, 6.0: 900},
    "ZN": {1.0: 3800, 1.5: 3100, 2.0: 2500, 3.0: 1800, 4.0: 1400},
    "RST304": {1.0: 2600, 1.5: 2100, 2.0: 1600, 3.0: 1000, 4.0: 700},
    "AL": {1.0: 4500, 1.5: 3800, 2.0: 3100, 3.0: 2300, 4.0: 1700},
}

try:
    from constants_adapter import (  # sinu vana programmi päris andmed
        WELDING_HOURLY_RATE,
        WELDING_SPEEDS,
        CLEANING_HOURLY_RATE,
        CLEANING_SPEED,
        OP_HOURLY_RATE,
        MATERIAL_PROPERTIES,
        CUTTING_SPEEDS,
    )
    CONFIG_SOURCE = "constants_adapter.py"
except Exception:
    OP_HOURLY_RATE = _FALLBACK_OP_HOURLY_RATE
    WELDING_HOURLY_RATE = _FALLBACK_WELDING_HOURLY_RATE
    CLEANING_HOURLY_RATE = _FALLBACK_CLEANING_HOURLY_RATE
    CLEANING_SPEED = _FALLBACK_CLEANING_SPEED
    WELDING_SPEEDS = _FALLBACK_WELDING_SPEEDS
    MATERIAL_PROPERTIES = _FALLBACK_MATERIAL_PROPERTIES
    CUTTING_SPEEDS = _FALLBACK_CUTTING_SPEEDS


def _cfg_float(section: str, key: str, default: float) -> float:
    try:
        value = cfg.get(section, key, default=default)
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _normalize_speed_keys(raw: Dict[str, Dict[Any, Any]]) -> Dict[str, Dict[float, float]]:
    """Tagab, et paksuse võtmed on float-id, sest veebivalik annab float väärtuse."""
    out: Dict[str, Dict[float, float]] = {}
    for mat_key, speeds in (raw or {}).items():
        out[mat_key] = {}
        for th, speed in (speeds or {}).items():
            try:
                out[mat_key][float(th)] = float(speed)
            except Exception:
                continue
    return out

CUTTING_SPEEDS = _normalize_speed_keys(CUTTING_SPEEDS)

# Kui vanas configis puuduvad keevituse/puhastuse kiirused, väldi tühja selectboxi ja nulliga jagamist.
if not WELDING_SPEEDS:
    WELDING_SPEEDS = {"MIG/MAG": 120.0, "TIG": 70.0}
try:
    if not CLEANING_SPEED or float(CLEANING_SPEED) <= 0:
        CLEANING_SPEED = 250.0
except Exception:
    CLEANING_SPEED = 250.0

DEFAULTS = {
    "margin": _cfg_float("defaults", "margin", 0.60),
    "laser_setup_min": _cfg_float("setup_times_min", "laser", 5.0),
    "bending_setup_min": _cfg_float("setup_times_min", "bending_setup_min", 10.0),
    "bending_per_bend_sec": _cfg_float("setup_times_min", "bending_per_bend_sec", 10.0),
    "welding_extra_min": _cfg_float("setup_times_min", "welding_extra", 10.0),
    "laser_rate_cs_zn": _cfg_float("rates", "laser_cs_zn", 150.0),
    "laser_rate_stainless_al": _cfg_float("rates", "laser_stainless_al", 225.0),
}

@dataclass
class DxfMetrics:
    width_mm: float
    height_mm: float
    cut_length_mm: float
    acad_release: str
    bend_count: int = 0
    bend_length_mm: float = 0.0


@dataclass
class PriceInput:
    material_key: str
    thickness_mm: float
    quantity: int = 1
    margin: float = DEFAULTS["margin"]
    include_laser_setup: bool = True
    include_bending: bool = False
    bend_count: int = 0
    weld_length_mm: float = 0.0
    weld_type: str = "MIG/MAG"
    clean_length_mm: float = 0.0
    shared_setup_per_piece: float | None = None


@dataclass
class PriceBreakdown:
    file_name: str
    material: str
    thickness_mm: float
    quantity: int
    width_mm: float
    height_mm: float
    cut_length_mm: float
    bend_count: int
    bend_length_mm: float
    material_cost_per: float
    cutting_cost_per: float
    laser_setup_per: float
    bending_cost_per: float
    welding_cost_per: float
    cleaning_cost_per: float
    base_sum_per: float
    margin: float
    price_per: float
    subtotal: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def euro(value: float) -> str:
    return f"{float(value):.2f} €"


# -----------------------------------------------------------------------------
# DXF GEOMEETRIA
# -----------------------------------------------------------------------------
def iter_geom(msp) -> Iterable[Any]:
    """Itereeri üle kõigi entiteetide, sh INSERT ploki virtuaalsed entiteedid."""
    for e in msp:
        try:
            if e.dxftype() == "INSERT":
                try:
                    for ve in e.virtual_entities():
                        try:
                            ve.transform(e.matrix44())
                        except Exception:
                            pass
                        try:
                            if (getattr(ve.dxf, "layer", "") in ("0", "", None)) and hasattr(e.dxf, "layer"):
                                ve.dxf.layer = e.dxf.layer
                        except Exception:
                            pass
                        yield ve
                except Exception:
                    continue
            else:
                yield e
        except Exception:
            continue


def is_cutting_layer(layer_name: str) -> bool:
    if not layer_name:
        return False
    n = layer_name.upper().replace("_", "").replace(" ", "")
    kws = [
        "LÕIGE", "L6IKUS", "LÖIKUS", "CUT", "CUTLINE", "PUNCH",
        "OUTER", "INTERIOR", "PROFILE", "PROFILES", "CONTOUR",
        "OUTLINE", "KONTUUR", "KONTUR", "GEOM", "GEOMETRY",
        "PROFIL", "LOOP", "CUTTING", "CONTOURS", "OUTLINES", "0",
    ]
    return any(k in n for k in kws)


def calculate_arc_length(p0: Pt, p1: Pt, bulge: float) -> float:
    dist_sq = (p1.x - p0.x) ** 2 + (p1.y - p0.y) ** 2
    if dist_sq == 0:
        return 0.0
    dist = math.sqrt(dist_sq)
    radius = dist * (bulge ** 2 + 1) / (4 * abs(bulge))
    angle = 4 * math.atan(abs(bulge))
    return radius * angle


def read_dxf(path: str):
    return ezdxf.readfile(path)


def dxf_metrics(doc) -> Tuple[float, float, float, str]:
    msp = doc.modelspace()

    def accumulate(only_cut_layers: bool = True):
        min_x = max_x = min_y = max_y = None
        total_len = 0.0
        for e in iter_geom(msp):
            try:
                layer = e.dxf.layer if e.dxf.hasattr("layer") else "0"
            except Exception:
                layer = "0"
            if only_cut_layers and not is_cutting_layer(layer):
                continue
            t = e.dxftype()
            try:
                if t == "LINE":
                    p0, p1 = e.dxf.start, e.dxf.end
                    total_len += math.hypot(p1.x - p0.x, p1.y - p0.y)
                    xs = [p0.x, p1.x]
                    ys = [p0.y, p1.y]
                elif t == "LWPOLYLINE":
                    pts = [Pt(p[0], p[1], (p[2] if len(p) > 2 else 0)) for p in e.get_points("xyb")]
                    for i in range(len(pts) - 1):
                        a, b = pts[i], pts[i + 1]
                        total_len += calculate_arc_length(a, b, a.bulge) if a.bulge else math.hypot(b.x - a.x, b.y - a.y)
                    if e.is_closed and pts:
                        a, b = pts[-1], pts[0]
                        total_len += calculate_arc_length(a, b, a.bulge) if a.bulge else math.hypot(b.x - a.x, b.y - a.y)
                    xs = [p.x for p in pts]
                    ys = [p.y for p in pts]
                elif t == "POLYLINE":
                    pts = list(e.points())
                    for i in range(len(pts) - 1):
                        a, b = pts[i], pts[i + 1]
                        total_len += math.hypot(b[0] - a[0], b[1] - a[1])
                    if getattr(e, "is_closed", False) and pts:
                        a, b = pts[-1], pts[0]
                        total_len += math.hypot(b[0] - a[0], b[1] - a[1])
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                elif t in ("SPLINE", "ARC", "CIRCLE", "ELLIPSE"):
                    pts = list(e.flattening(distance=0.05)) if t == "SPLINE" else list(e.flattening(sagitta=0.05))
                    for i in range(len(pts) - 1):
                        a, b = pts[i], pts[i + 1]
                        total_len += math.hypot(b[0] - a[0], b[1] - a[1])
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                else:
                    xs = ys = []

                if xs and ys:
                    if min_x is None:
                        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
                    else:
                        min_x = min(min_x, *xs)
                        max_x = max(max_x, *xs)
                        min_y = min(min_y, *ys)
                        max_y = max(max_y, *ys)
            except Exception:
                continue
        return min_x, max_x, min_y, max_y, total_len

    min_x, max_x, min_y, max_y, total_len = accumulate(True)
    if min_x is None:
        min_x, max_x, min_y, max_y, total_len = accumulate(False)

    if min_x is None:
        return 0.0, 0.0, 0.0, getattr(doc, "acad_release", "?")

    return round(max_x - min_x, 1), round(max_y - min_y, 1), round(total_len, 1), getattr(doc, "acad_release", "?")


def calculate_bend_details_from_ezdxf(doc) -> Tuple[int, float]:
    msp = doc.modelspace()
    layer_linetype: Dict[str, str] = {}
    try:
        for layer in doc.layers:
            try:
                layer_linetype[(layer.dxf.name or "").upper()] = (layer.dxf.linetype or "").upper()
            except Exception:
                continue
    except Exception:
        pass

    stopwords = (
        "EXTEND", "EXTENSION", "EXT", "AUX", "AUXILIARY", "CONSTR",
        "CONSTRUCTION", "REF", "REFERENCE", "PROJ", "PROJECTION", "DIM",
        "DIMENSION", "HELP",
    )

    def has_stopword(name: str) -> bool:
        n = (name or "").upper().replace("-", " ").replace(".", " ")
        return any(sw in n for sw in stopwords)

    def is_bend_layer(name: str) -> bool:
        n_raw = (name or "").upper()
        if has_stopword(n_raw):
            return False
        n = n_raw.replace("_", " ").replace("-", " ")
        tokens = n.split()
        if "BEND" in tokens:
            return True
        if any(tok.startswith("BEND") and tok != "BEND" for tok in tokens):
            return False
        join = n.replace(" ", "")
        return any(k in join for k in ("PAINUT", "PAINUTUS", "KANT", "KANTIMINE", "CENTERLINE", "CENTERLINES", "UPCENTERLINES", "DOWNCENTERLINES", "CENTER"))

    def is_bend_linetype(lt: str, layer_name: str) -> bool:
        if has_stopword(layer_name):
            return False
        s = (lt or "").upper()
        return any(k in s for k in ("CENTER", "DASH", "HIDDEN", "DOT"))

    total_segments: List[Tuple[float, float, float, float]] = []

    for e in iter_geom(msp):
        try:
            t = e.dxftype()
            layer = (e.dxf.layer if e.dxf.hasattr("layer") else "") or ""
            ent_lt = (e.dxf.linetype if e.dxf.hasattr("linetype") else "") or ""
            eff_lt = ent_lt if ent_lt.upper() not in ("", "BYLAYER") else layer_linetype.get(layer.upper(), "")
            if not (is_bend_layer(layer) or is_bend_linetype(eff_lt, layer)):
                continue

            if t == "LINE":
                total_segments.append((e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
            elif t == "LWPOLYLINE":
                pts = [Pt(p[0], p[1], (p[2] if len(p) > 2 else 0)) for p in e.get_points("xyb")]
                for i in range(len(pts) - 1):
                    p0, p1 = pts[i], pts[i + 1]
                    total_segments.append((p0.x, p0.y, p1.x, p1.y))
                if getattr(e, "is_closed", False) and pts:
                    p0, p1 = pts[-1], pts[0]
                    total_segments.append((p0.x, p0.y, p1.x, p1.y))
            elif t == "POLYLINE":
                pts = list(e.points())
                for i in range(len(pts) - 1):
                    p0, p1 = pts[i], pts[i + 1]
                    total_segments.append((p0[0], p0[1], p1[0], p1[1]))
                if getattr(e, "is_closed", False) and pts:
                    p0, p1 = pts[-1], pts[0]
                    total_segments.append((p0[0], p0[1], p1[0], p1[1]))
            elif t in ("SPLINE", "ARC"):
                pts = list(e.flattening(distance=0.5)) if t == "SPLINE" else list(e.flattening(sagitta=0.5))
                for i in range(len(pts) - 1):
                    p0, p1 = pts[i], pts[i + 1]
                    total_segments.append((p0[0], p0[1], p1[0], p1[1]))
        except Exception:
            continue

    if not total_segments:
        return 0, 0.0

    norm = []
    for x0, y0, x1, y1 in total_segments:
        a = (round(x0, 2), round(y0, 2))
        b = (round(x1, 2), round(y1, 2))
        norm.append(tuple(sorted([a, b])))
    unique_segments = list(set(norm))
    total_length = sum(math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in unique_segments)
    return len(unique_segments), round(total_length, 2)


def analyze_dxf(path: str) -> DxfMetrics:
    doc = read_dxf(path)
    width, height, cut_len, ver = dxf_metrics(doc)
    bends, bend_len = calculate_bend_details_from_ezdxf(doc)
    return DxfMetrics(width, height, cut_len, ver, bends, bend_len)


# -----------------------------------------------------------------------------
# HINNA ARVUTAMINE
# -----------------------------------------------------------------------------
def laser_rate_for_material(mat_key: str, mat_label: str = "") -> float:
    key = (mat_key or "").upper()
    label = (mat_label or "").upper()
    if (
        key.startswith("RST") or key.startswith("AW") or key.startswith("AL")
        or "SS" in key or "304" in key or "316" in key or "430" in key
        or "INOX" in key or "STAIN" in key or "ALU" in key or "ALUMIN" in key
        or "ROOSTEVABA" in label or "ALUMIINIUM" in label
    ):
        return float(DEFAULTS["laser_rate_stainless_al"])
    return float(DEFAULTS["laser_rate_cs_zn"])


def available_materials() -> Dict[str, str]:
    return {k: v.get("label", k) for k, v in MATERIAL_PROPERTIES.items()}


def available_thicknesses(material_key: str) -> List[float]:
    return sorted(CUTTING_SPEEDS.get(material_key, {}).keys())


def calculate_price(file_name: str, metrics: DxfMetrics, data: PriceInput) -> PriceBreakdown:
    material_key = data.material_key
    mat = MATERIAL_PROPERTIES.get(material_key, {})
    mat_label = mat.get("label", material_key)
    th = float(data.thickness_mm)
    qty = max(int(data.quantity or 1), 1)
    speed = CUTTING_SPEEDS.get(material_key, {}).get(th, 0.0)

    laser_rate = laser_rate_for_material(material_key, mat_label)
    cutting_cost = (metrics.cut_length_mm / speed / 60.0) * laser_rate if speed > 0 else 0.0

    laser_setup_per = 0.0
    if data.include_laser_setup:
        if data.shared_setup_per_piece is not None:
            laser_setup_per = float(data.shared_setup_per_piece)
        else:
            laser_setup_per = (float(DEFAULTS["laser_setup_min"]) / 60.0) * OP_HOURLY_RATE / qty

    density = float(mat.get("density_kg_m3", 0.0))
    price_kg = float(mat.get("price_eur_kg", 0.0))
    area_mm2 = float(metrics.width_mm) * float(metrics.height_mm)
    volume_m3 = (area_mm2 / 1_000_000.0) * (th / 1000.0)
    material_cost = volume_m3 * density * price_kg

    bend_count = int(data.bend_count or metrics.bend_count or 0)
    bending_cost = 0.0
    if data.include_bending and bend_count > 0:
        bend_time_s = bend_count * float(DEFAULTS["bending_per_bend_sec"])
        setup_cost_per = (float(DEFAULTS["bending_setup_min"]) / 3600.0) * OP_HOURLY_RATE / qty
        bending_cost = (bend_time_s / 3600.0) * OP_HOURLY_RATE + setup_cost_per

    welding_cost = 0.0
    weld_len = float(data.weld_length_mm or 0.0)
    if weld_len > 0:
        w_speed = WELDING_SPEEDS.get(data.weld_type, 0.0)
        if w_speed > 0:
            welding_time_min = weld_len / w_speed
            total_welding_time_min = (welding_time_min * qty) + float(DEFAULTS["welding_extra_min"])
            welding_cost = ((total_welding_time_min / 60.0) * WELDING_HOURLY_RATE) / qty

    cleaning_cost = 0.0
    clean_len = float(data.clean_length_mm or 0.0)
    if clean_len > 0:
        cleaning_time_min = clean_len / CLEANING_SPEED
        total_cleaning_time_min = cleaning_time_min * qty
        cleaning_cost = ((total_cleaning_time_min / 60.0) * CLEANING_HOURLY_RATE) / qty

    base_sum = material_cost + cutting_cost + laser_setup_per + bending_cost + welding_cost + cleaning_cost
    margin = float(data.margin or 0.0)
    price_per = base_sum * (1.0 + margin)
    subtotal = price_per * qty

    return PriceBreakdown(
        file_name=os.path.basename(file_name),
        material=mat_label,
        thickness_mm=th,
        quantity=qty,
        width_mm=metrics.width_mm,
        height_mm=metrics.height_mm,
        cut_length_mm=metrics.cut_length_mm,
        bend_count=bend_count,
        bend_length_mm=metrics.bend_length_mm,
        material_cost_per=material_cost,
        cutting_cost_per=cutting_cost,
        laser_setup_per=laser_setup_per,
        bending_cost_per=bending_cost,
        welding_cost_per=welding_cost,
        cleaning_cost_per=cleaning_cost,
        base_sum_per=base_sum,
        margin=margin,
        price_per=price_per,
        subtotal=subtotal,
    )
