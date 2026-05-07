# -*- coding: utf-8 -*-
import csv
import io
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

def image_file_to_base64(path: Path) -> str:
    try:
        return base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return ""


def find_logo_path() -> Path | None:
    assets_dir = Path(__file__).parent / "assets"
    candidates = [
        assets_dir / "ransi_metall_logo.png",
        assets_dir / "ransi-metall-logo.png",
        assets_dir / "logo.png",
        assets_dir / "ransi_metall_logo.jpg",
        assets_dir / "ransi-metall-logo.jpg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


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
            max-width: 980px;
            padding-top: 2rem;
            padding-bottom: 2rem;
            margin-left: auto;
            margin-right: auto;
        }}
        h1 {{
            text-align: center;
        }}
        .hero-box {{
            text-align: center;
        }}
        .logo-wrap {{
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 0.2rem 0 1.15rem 0;
        }}
        .logo-wrap img {{
            max-width: 360px;
            width: min(100%, 360px);
            height: auto;
            display: block;
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
        .price-card {{
            background: rgba(255, 255, 255, 0.93);
            border: 1px solid #dfe7f1;
            border-radius: 18px;
            overflow: hidden;
            margin-bottom: 1rem;
            box-shadow: 0 6px 18px rgba(16, 24, 40, 0.06);
        }}
        .price-card-top {{
            padding: 0.85rem;
            background: #f5f8fc;
            border-bottom: 1px solid #e9eef5;
        }}
        .preview-image {{
            width: 100%;
            border-radius: 12px;
            border: 1px solid #dde5ef;
            background: #f7f9fc;
            display: block;
        }}
        .price-card-body {{
            padding: 0.95rem 1rem 1rem 1rem;
        }}
        .file-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: #10233f;
            margin-bottom: 0.3rem;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.45rem 1rem;
            margin-top: 0.6rem;
        }}
        .meta-item {{
            color: #465467;
            font-size: 0.94rem;
        }}
        .meta-item strong {{
            color: #10233f;
        }}
        .price-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.8rem;
            margin-top: 0.85rem;
        }}
        .price-pill {{
            background: #f7fafd;
            border: 1px solid #e3eaf3;
            border-radius: 12px;
            padding: 0.65rem 0.8rem;
            min-width: 150px;
        }}
        .price-pill-label {{
            color: #667085;
            font-size: 0.83rem;
            margin-bottom: 0.18rem;
        }}
        .price-pill-value {{
            color: #10233f;
            font-weight: 700;
            font-size: 1.02rem;
        }}
        .summary-box {{
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid #dfe7f1;
            border-radius: 18px;
            padding: 1rem 1.1rem;
            margin-top: 0.75rem;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

VAT_RATE = 0.22
MAX_SETUP_SPLIT_QTY = 200
LEADS_FILE = Path("leads.csv")
GOOGLE_SHEETS_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "https://script.google.com/macros/s/AKfycbxxAeB5sHXGMefu3j2Z-YI_wh8LkgRjA7NtTqKzDZFMMX_u8F-xJixHh-WtIofqLSs/exec")
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

@st.cache_data(show_spinner=False)
def render_dxf_preview_base64(file_bytes: bytes, file_name: str) -> str:
    try:
        import matplotlib.pyplot as plt
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    except Exception:
        return ""

    tmp_path = None
    try:
        suffix = Path(file_name).suffix or ".dxf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        doc = ezdxf.readfile(tmp_path)
        msp = doc.modelspace()
        fig = plt.figure(figsize=(4.0, 3.0), dpi=150)
        ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
        ax.set_facecolor("#f7f9fc")
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)
        ax.autoscale()
        ax.margins(0.08)
        ax.set_aspect("equal")
        ax.axis("off")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.08, facecolor="#f7f9fc")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def metric_value(metrics, names, default=None):
    for name in names:
        if isinstance(metrics, dict) and name in metrics:
            return metrics.get(name)
        if hasattr(metrics, name):
            return getattr(metrics, name)
    return default


def extract_dimensions_mm(metrics):
    width = metric_value(metrics, ["width_mm", "bbox_width_mm", "width", "x_size_mm"])
    height = metric_value(metrics, ["height_mm", "bbox_height_mm", "height", "y_size_mm"])
    try:
        if width is not None and height is not None:
            return float(width), float(height)
    except Exception:
        pass
    return None, None



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


logo_path = find_logo_path()
if logo_path is not None:
    logo_b64 = image_file_to_base64(logo_path)
    if logo_b64:
        logo_mime = "image/png" if logo_path.suffix.lower() == ".png" else "image/jpeg"
        st.markdown(
            f"""
            <div class="logo-wrap">
                <img src="data:{logo_mime};base64,{logo_b64}" alt="Ransi Metall logo">
            </div>
            """,
            unsafe_allow_html=True,
        )

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
    '<div class="muted-text">Kalkulaatori kasutamiseks palume sisestada ettevõtte nimi ja e-posti aadress. Kasutame neid andmeid ainult kalkulaatori kasutuse registreerimiseks ning vajadusel ühenduse võtmiseks.</div>',
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
    accept_multiple_files=True,
    help="Lae üles ainult .dxf failid. Mobiilis salvesta fail enne telefoni Files/Failid kausta.",
)

if uploaded_files:
    wrong_files = [uploaded.name for uploaded in uploaded_files if not uploaded.name.lower().endswith(".dxf")]
    if wrong_files:
        st.error("Palun lae üles ainult DXF-failid.")
        for file_name in wrong_files:
            st.write(f"- {file_name}")
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

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
        preview_b64 = render_dxf_preview_base64(uploaded.getvalue(), uploaded.name)
        prepared.append((uploaded.name, metrics, file_key, preview_b64))
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
    st.caption("Iga faili juures kuvatakse eelvaade, mõõdud ja kogus. Vajadusel saad faili loendist eemaldada.")

quantity_by_key = {}
for i, (file_name, metrics, file_key, preview_b64) in enumerate(prepared):
    width_mm, height_mm = extract_dimensions_mm(metrics)
    st.markdown('<div class="price-card"><div class="price-card-top">', unsafe_allow_html=True)
    cols = st.columns([1.15, 2.2, 0.95, 0.8])

    with cols[0]:
        if preview_b64:
            st.markdown(f'<img class="preview-image" src="data:image/png;base64,{preview_b64}" alt="DXF eelvaade">', unsafe_allow_html=True)
        else:
            st.info("Eelvaade puudub")

    with cols[1]:
        st.markdown(f'<div class="file-title">{file_name}</div>', unsafe_allow_html=True)
        meta_lines = []
        if width_mm is not None and height_mm is not None:
            meta_lines.append(f'<div class="meta-item"><strong>Mõõdud:</strong> {width_mm:.1f} × {height_mm:.1f} mm</div>')
        meta_lines.append(f'<div class="meta-item"><strong>Materjal:</strong> {selected_label}</div>')
        meta_lines.append(f'<div class="meta-item"><strong>Paksus:</strong> {float(thickness_mm):g} mm</div>')
        st.markdown('<div class="meta-grid">' + ''.join(meta_lines) + '</div>', unsafe_allow_html=True)

    with cols[2]:
        quantity_by_key[file_key] = int(st.number_input(
            "Kogus",
            min_value=1,
            value=int(st.session_state.get(f"qty_{file_key}", 1)),
            step=1,
            key=f"qty_{file_key}",
        ))

    with cols[3]:
        st.write("")
        if st.button("Kustuta", key=f"delete_precalc_{i}_{file_key}"):
            st.session_state["deleted_upload_keys"].add(file_key)
            st.rerun()

    st.markdown('</div></div>', unsafe_allow_html=True)

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

    total_qty_for_group = sum(int(quantity_by_key.get(file_key, 1)) for _, _, file_key, _ in prepared)
    billable_setup_qty = min(max(1, total_qty_for_group), MAX_SETUP_SPLIT_QTY)
    setup_cost_total = (float(DEFAULTS.get("laser_setup_min", 10.0)) / 60.0) * float(OP_HOURLY_RATE)
    shared_setup_per_piece = setup_cost_total / billable_setup_qty

for file_name, metrics, file_key, preview_b64 in prepared:
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
    "quantity": "; ".join([f"{name}: {quantity_by_key.get(key, 1)}" for name, _, key, _ in prepared]),
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

rows_by_key = {row.get("_upload_key"): row for row in rows}

for file_name, metrics, file_key, preview_b64 in prepared:
    row = rows_by_key.get(file_key)
    if not row:
        continue

    width_mm, height_mm = extract_dimensions_mm(metrics)
    subtotal_without_vat = float(row["subtotal"])
    total_with_vat_row = subtotal_without_vat * (1 + VAT_RATE)

    st.markdown('<div class="price-card">', unsafe_allow_html=True)
    cols = st.columns([1.15, 2.4])
    with cols[0]:
        st.markdown('<div class="price-card-top">', unsafe_allow_html=True)
        if preview_b64:
            st.markdown(f'<img class="preview-image" src="data:image/png;base64,{preview_b64}" alt="DXF eelvaade">', unsafe_allow_html=True)
        else:
            st.info("Eelvaade puudub")
        st.markdown('</div>', unsafe_allow_html=True)

    with cols[1]:
        st.markdown('<div class="price-card-body">', unsafe_allow_html=True)
        st.markdown(f'<div class="file-title">{row["file_name"]}</div>', unsafe_allow_html=True)
        meta_lines = []
        if width_mm is not None and height_mm is not None:
            meta_lines.append(f'<div class="meta-item"><strong>Mõõdud:</strong> {width_mm:.1f} × {height_mm:.1f} mm</div>')
        meta_lines.append(f'<div class="meta-item"><strong>Materjal:</strong> {selected_label}</div>')
        meta_lines.append(f'<div class="meta-item"><strong>Paksus:</strong> {float(thickness_mm):g} mm</div>')
        meta_lines.append(f'<div class="meta-item"><strong>Kogus:</strong> {int(row.get("quantity", 1))} tk</div>')
        st.markdown('<div class="meta-grid">' + ''.join(meta_lines) + '</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="price-row">
                <div class="price-pill">
                    <div class="price-pill-label">Hind/tk ilma KM-ta</div>
                    <div class="price-pill-value">{euro(float(row["price_per"]))}</div>
                </div>
                <div class="price-pill">
                    <div class="price-pill-label">Kokku ilma KM-ta</div>
                    <div class="price-pill-value">{euro(subtotal_without_vat)}</div>
                </div>
                <div class="price-pill">
                    <div class="price-pill-label">Kokku KM-ga</div>
                    <div class="price-pill-value">{euro(total_with_vat_row)}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="summary-box">', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.metric("Kokku ilma KM-ta", euro(total_without_vat))
with c2:
    st.metric("Kokku KM-ga 22%", euro(total_with_vat))
st.markdown('</div>', unsafe_allow_html=True)

st.caption("Hind on indikatiivne.")

st.markdown(
    "<p style='text-align:center; color:#465467; margin-top:24px;'>Lisainfo saamiseks kirjutage: <b>info@ransimetall.ee</b></p>",
    unsafe_allow_html=True
)

st.markdown('</div>', unsafe_allow_html=True)
