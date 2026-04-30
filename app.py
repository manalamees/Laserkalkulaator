# -*- coding: utf-8 -*-
import csv
import hashlib
import json
import os
import re
import tempfile
import urllib.request
import base64
from datetime import datetime
from pathlib import Path

import streamlit as st

from pricing_engine import (
    DEFAULTS,
    PriceInput,
    analyze_dxf,
    available_materials,
    available_thicknesses,
    calculate_price,
    euro,
)

st.set_page_config(page_title="Laserlõikuse hinnakalkulaator", layout="wide")


def get_background_image_base64() -> str:
    image_path = Path(__file__).parent / "assets" / "laser_factory_background.png"
    try:
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
    except Exception:
        return ""

BACKGROUND_IMAGE_B64 = get_background_image_base64()

st.markdown(
    f"""
    <style>
        [data-testid="stAppViewContainer"] {{
            background:
                linear-gradient(rgba(246, 249, 252, 0.84), rgba(246, 249, 252, 0.90)),
                url("data:image/png;base64,{BACKGROUND_IMAGE_B64}");
            background-size: cover;
            background-position: center top;
            background-attachment: fixed;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            background: transparent;
        }}
        .stApp {{
            background: transparent;
        }}
        [data-testid="stHeader"] {{
            background: rgba(246, 249, 252, 0.72);
            backdrop-filter: blur(8px);
        }}
        .block-container {{
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 2rem;
        }}
        .hero-box, .section-box {{
            background: rgba(255, 255, 255, 0.88);
            backdrop-filter: blur(8px);
            border: 1px solid #e8edf3;
            border-radius: 18px;
            padding: 1.35rem 1.4rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
            margin-bottom: 1rem;
        }}
        .hero-title {{
            font-size: 1.15rem;
            font-weight: 700;
            color: #10233f;
            margin-bottom: 0.55rem;
        }}
        .hero-text, .muted-text {{
            color: #465467;
            line-height: 1.65;
            font-size: 0.98rem;
        }}
        .mini-note {{
            color: #667085;
            font-size: 0.92rem;
            margin-top: 0.25rem;
        }}
        .section-label {{
            font-size: 1.45rem;
            font-weight: 700;
            margin-top: 0.4rem;
            margin-bottom: 0.25rem;
            color: #10233f;
        }}
        .subtle-box {{
            background: rgba(247, 250, 252, 0.82);
            border: 1px solid #e8edf3;
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin-top: 0.5rem;
            margin-bottom: 0.75rem;
        }}
        .service-list {{
            margin: 0.35rem 0 0 0;
            padding-left: 1.15rem;
            color: #465467;
            line-height: 1.7;
        }}
        .service-list li {{
            margin-bottom: 0.15rem;
        }}
        .table-head {{
            font-weight: 700;
            color: #10233f;
            padding-bottom: 0.35rem;
        }}
        .row-divider {{
            border-top: 1px solid #eef2f6;
            margin: 0.2rem 0 0.45rem 0;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

VAT_RATE = 0.22
MAX_SETUP_SPLIT_QTY = 200
LEADS_FILE = Path("leads.csv")
GOOGLE_SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxxAeB5sHXGMefu3j2Z-YI_wh8LkgRjA7NtTqKzDZFMMX_u8F-xJixHh-WtIofqLSs/exec"
UPLOAD_DIR = Path("lead_uploads")


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (email or "").strip()))


def safe_filename(name: str) -> str:
    name = os.path.basename(name or "file.dxf")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "file.dxf"


def uploaded_file_key(index: int, uploaded) -> str:
    size = getattr(uploaded, "size", 0) or 0
    raw = f"{index}|{uploaded.name}|{size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()



def send_lead_to_google_sheets(row: dict) -> bool:
    """Saadab kalkulaatori kasutuse Google Sheetsi Apps Script webhooki kaudu."""
    if not GOOGLE_SHEETS_WEBHOOK_URL:
        return False

    try:
        payload = json.dumps(row, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            GOOGLE_SHEETS_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return response.status == 200 and '"ok"' in body
    except Exception:
        return False


def append_lead(row: dict) -> None:
    send_lead_to_google_sheets(row)

    fieldnames = [
        "timestamp",
        "event",
        "company",
        "contact_name",
        "email",
        "phone",
        "material",
        "thickness_mm",
        "quantity",
        "files",
        "total_without_vat",
        "total_with_vat",
        "price_per_first_file",
        "comment",
        "saved_files_folder",
    ]
    try:
        exists = LEADS_FILE.exists()
        with LEADS_FILE.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    except PermissionError:
        backup_file = LEADS_FILE.with_name(
            f"leads_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        with backup_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def save_uploaded_files(uploaded_files, company: str, email: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug_source = f"{company}_{email}_{ts}"
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", slug_source)[:80]
    folder = UPLOAD_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)
    for uploaded in uploaded_files:
        out = folder / safe_filename(uploaded.name)
        out.write_bytes(uploaded.getbuffer())
    return str(folder)


def log_calculation_once(payload: dict) -> None:
    key_src = "|".join(str(payload.get(k, "")) for k in [
        "event", "company", "email", "material", "thickness_mm", "quantity", "files", "total_without_vat"
    ])
    key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    if st.session_state.get("last_logged_calc") != key:
        append_lead(payload)
        st.session_state["last_logged_calc"] = key


st.title("Laserlõikuse hinnakalkulaator")

st.markdown(
    """
    <div class="hero-box">
        <div class="hero-title">Tahad teada, kui palju laserlõikus ligikaudu maksab?</div>
        <div class="hero-text">
            Laadi kalkulaatorisse DXF-fail, vali materjal, paksus ja kogus ning saad esmase hinnangu laserlõikuse maksumusele.
            Hind sõltub eelkõige materjalist, paksusest, detaili keerukusest, kogusest ja laseri võimekusest.
            Selle kalkulaatori arvestuse aluseks on 12 kW laser.
        </div>
        <div class="mini-note">
            Kalkulaatoris kuvatud hind on indikatiivne ning lõplik hind sõltub faili tehnilisest ülevaatusest.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="section-label">Kontaktandmed</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="muted-text">Kalkulaatori kasutamiseks palume sisestada ettevõtte nime ja e-posti aadressi. Kasutame neid andmeid ainult kalkulaatori kasutuse registreerimiseks ning vajadusel ühenduse võtmiseks.</div>',
    unsafe_allow_html=True,
)

col_a, col_b = st.columns(2)
with col_a:
    company = st.text_input("Ettevõtte nimi *", key="company")
    contact_name = st.text_input("Kontaktisik", key="contact_name")
with col_b:
    email = st.text_input("E-mail *", key="email")
    phone = st.text_input("Telefon", key="phone")

consent = st.checkbox(
    "Nõustun, et minu andmeid kasutatakse kalkulaatori kasutuse registreerimiseks ja vajadusel ühenduse võtmiseks. Minu andmeid ei jagata kolmandatele osapooltele. *"
)

missing = []
if not company.strip():
    missing.append("ettevõtte nimi")
if not email.strip():
    missing.append("e-mail")
elif not is_valid_email(email):
    missing.append("korrektne e-mail")
if not consent:
    missing.append("nõusolek")

if missing:
    st.info("Kalkulaatori avamiseks täida: " + ", ".join(missing) + ".")
    st.stop()

st.markdown('<div class="section-box">', unsafe_allow_html=True)
st.markdown('<div class="section-label">Arvutuse andmed</div>', unsafe_allow_html=True)
st.markdown('<div class="muted-text">Laadi üles DXF-fail(id), vali materjal ja paksus ning määra kogus iga detaili jaoks eraldi.</div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    "Lae DXF fail(id) üles",
    type=["dxf"],
    accept_multiple_files=True,
)

if "deleted_upload_keys" not in st.session_state:
    st.session_state["deleted_upload_keys"] = set()

active_uploaded_files = []
for idx, uploaded in enumerate(uploaded_files or []):
    file_key = uploaded_file_key(idx, uploaded)
    if file_key not in st.session_state["deleted_upload_keys"]:
        active_uploaded_files.append((idx, file_key, uploaded))

materials = available_materials()
if not materials:
    st.error("Materjalide nimekiri on tühi. Palun võta meiega ühendust.")
    st.stop()

material_keys = list(materials.keys())
material_labels = [materials[k] for k in material_keys]

col1, col2 = st.columns(2)

with col1:
    default_material_key = str(DEFAULTS.get("default_material_key", "RST") or "RST")
    default_index = material_keys.index(default_material_key) if default_material_key in material_keys else 0
    selected_label = st.selectbox(
        "Materjal",
        options=material_labels,
        index=default_index,
        key="selected_material_label",
    )
    material_key = material_keys[material_labels.index(selected_label)]

with col2:
    thicknesses = available_thicknesses(material_key)
    if not thicknesses:
        st.error(f"Materjalil '{selected_label}' puudub hinnastamiseks vajalik paksuse info.")
        st.stop()
    thickness_mm = st.selectbox(
        "Paksus",
        options=thicknesses,
        index=0,
        format_func=lambda x: f"{float(x):g} mm",
        key=f"thickness_for_{material_key}",
    )

if not uploaded_files:
    st.info("Lisa vähemalt üks DXF-fail, et indikatiivne hind kuvada.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

if not active_uploaded_files:
    st.info("Kõik üleslaetud detailid on loendist eemaldatud. Lisa uus DXF-fail või eemalda fail üleslaadimise väljast ja lae uuesti üles.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

prepared = []
errors = []

for original_index, file_key, uploaded in active_uploaded_files:
    suffix = os.path.splitext(uploaded.name)[1] or ".dxf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getbuffer())
        tmp_path = tmp.name

    try:
        metrics = analyze_dxf(tmp_path)
        prepared.append((uploaded.name, metrics, file_key))
    except Exception:
        errors.append(uploaded.name)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

if errors:
    st.error("Mõnda DXF-faili ei õnnestunud töödelda. Palun kontrolli faili või saada see meile ülevaatamiseks.")
    for file_name in errors:
        st.write(f"- {file_name}")

if prepared:
    st.markdown("**Üleslaetud detailid**")
    st.caption("Muuda kogust iga detaili real eraldi. Soovi korral saad detaili loendist eemaldada.")

quantity_by_key = {}
for i, (file_name, metrics, file_key) in enumerate(prepared):
    cols = st.columns([4.2, 1.1, 1.0])
    cols[0].write(file_name)
    quantity_by_key[file_key] = int(cols[1].number_input(
        "Kogus",
        min_value=1,
        value=int(st.session_state.get(f"qty_{file_key}", 1)),
        step=1,
        key=f"qty_{file_key}",
        label_visibility="collapsed",
    ))
    if cols[2].button("Kustuta", key=f"delete_precalc_{i}_{file_key}"):
        st.session_state["deleted_upload_keys"].add(file_key)
        st.rerun()

rows = []
margin = float(DEFAULTS.get("margin", 0.6) or 0.6)
include_setup = True
share_setup = True
include_bending = False
weld_length_mm = 0.0
clean_length_mm = 0.0
weld_type = "MIG/MAG"

shared_setup_per_piece = None
if include_setup and share_setup and prepared:
    from pricing_engine import OP_HOURLY_RATE

    total_qty_for_group = sum(int(quantity_by_key.get(file_key, 1)) for _, _, file_key in prepared)
    billable_setup_qty = min(max(1, total_qty_for_group), MAX_SETUP_SPLIT_QTY)
    setup_cost_total = (float(DEFAULTS.get("laser_setup_min", 10.0)) / 60.0) * float(OP_HOURLY_RATE)
    shared_setup_per_piece = setup_cost_total / billable_setup_qty

for file_name, metrics, file_key in prepared:
    try:
        data = PriceInput(
            material_key=material_key,
            thickness_mm=float(thickness_mm),
            quantity=int(quantity_by_key.get(file_key, 1)),
            margin=margin,
            include_laser_setup=include_setup,
            include_bending=include_bending,
            bend_count=0,
            weld_length_mm=weld_length_mm,
            weld_type=weld_type,
            clean_length_mm=clean_length_mm,
            shared_setup_per_piece=shared_setup_per_piece,
        )
        bd = calculate_price(file_name, metrics, data)
        row = bd.to_dict()
        row["_upload_key"] = file_key
        rows.append(row)
    except Exception:
        errors.append(file_name)

if not rows:
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

total_without_vat = sum(float(row["subtotal"]) for row in rows)
total_with_vat = total_without_vat * (1 + VAT_RATE)
file_names = "; ".join([row["file_name"] for row in rows])
first_price = float(rows[0]["price_per"]) if rows else 0.0

lead_payload = {
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "event": "calculation",
    "company": company.strip(),
    "contact_name": contact_name.strip(),
    "email": email.strip(),
    "phone": phone.strip(),
    "material": selected_label,
    "thickness_mm": float(thickness_mm),
    "quantity": "; ".join([f"{name}: {quantity_by_key.get(key, 1)}" for name, _, key in prepared]),
    "files": file_names,
    "total_without_vat": round(total_without_vat, 2),
    "total_with_vat": round(total_with_vat, 2),
    "price_per_first_file": round(first_price, 2),
    "comment": "",
    "saved_files_folder": "",
}
log_calculation_once(lead_payload)

st.markdown('<div class="section-label">Hinnanguline hind</div>', unsafe_allow_html=True)
st.markdown('<div class="muted-text">Allpool on iga üleslaetud detaili indikatiivne hinnang ning koondsumma.</div>', unsafe_allow_html=True)

st.markdown("<div class='row-divider'></div>", unsafe_allow_html=True)
header_cols = st.columns([3.0, 1.6, 0.9, 0.8, 1.45, 1.45, 1.35])
headers = [
    "Detail",
    "Materjal",
    "Paksus",
    "Kogus",
    "Hind/tk ilma KM-ta",
    "Kokku ilma KM-ta",
    "Kokku KM-ga",
]
for col, header in zip(header_cols, headers):
    col.markdown(f"<div class='table-head'>{header}</div>", unsafe_allow_html=True)

for row in rows:
    subtotal_without_vat = float(row["subtotal"])
    cols = st.columns([3.0, 1.6, 0.9, 0.8, 1.45, 1.45, 1.35])
    cols[0].write(row["file_name"])
    cols[1].write(selected_label)
    cols[2].write(f"{float(thickness_mm):g} mm")
    cols[3].write(int(row.get("quantity", 1)))
    cols[4].write(euro(float(row["price_per"])))
    cols[5].write(euro(subtotal_without_vat))
    cols[6].write(euro(subtotal_without_vat * (1 + VAT_RATE)))
    st.markdown("<div class='row-divider'></div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.metric("Kokku ilma KM-ta", euro(total_without_vat))
with c2:
    st.metric("Kokku KM-ga 22%", euro(total_with_vat))

st.caption("Hind on indikatiivne.")
st.markdown('</div>', unsafe_allow_html=True)
