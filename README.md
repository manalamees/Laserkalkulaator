# Laserlõikuse hinnakalkulaator — veebiversiooni algus

See on esimene Streamlit veebiversioon olemasolevast PyQt5 DXF hinnakalkulaatorist.

## Käivitamine Windowsis

Ava PowerShell selles kaustas ja käivita:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Kui PowerShell ei luba `Activate.ps1` käivitada, kasuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Failid

- `app.py` — veebileht, kuhu saab DXF faili üles laadida.
- `pricing_engine.py` — arvutusmootor ilma PyQt5-ta.
- `requirements.txt` — vajalikud Python paketid.

## Järgmised sammud

1. Tõsta oma päris materjalihinnad ja lõikekiirused `pricing_engine.py` faili.
2. Kontrolli ühe test-DXF-iga, kas tulemus klapib vana PyQt5 programmi hinnaga.
3. Lisa PDF pakkumise eksport.
4. Lisa kliendi andmed.
5. Hiljem saab selle panna päris veebiserverisse või teha FastAPI versiooni.


## Vana programmi andmete kasutamine

See versioon proovib automaatselt lugeda sinu vana programmi andmeid failist `constants_adapter.py`.

Pane vanast programmi kaustast siia samasse kausta juurde:

```text
constants_adapter.py
config_manager.py        # kui olemas
settings.ini/config.ini  # kui config_manager seda kasutab
```

Kui `constants_adapter.py` on kõrval, kuvatakse veebis: `Seadete allikas: constants_adapter.py`.
Kui seda ei ole, kuvatakse: `Seadete allikas: fallback_demo_values` ja hinnad on ainult näidisandmetega.

Vajalikud muutujad `constants_adapter.py` sees:

```python
WELDING_HOURLY_RATE
WELDING_SPEEDS
CLEANING_HOURLY_RATE
CLEANING_SPEED
OP_HOURLY_RATE
MATERIAL_PROPERTIES
CUTTING_SPEEDS
```


## v2 parandus

- Laseri seadistus on vaikimisi sees, nagu vanas PyQt programmis.
- Lisatud on valik seadistuse jagamiseks sama materjali+paksuse koguse peale.
- Kui omahind tuleb liiga madal (~8 €), kontrolli, et „Kaasa laseri seadistus“ oleks sees.


## Muudatus v4
Kliendile kuvatakse detailide ülevaade: iga DXF-faili hind/tk, kogus, detaili kogusumma ning koondhind ilma KM-ta ja KM-ga. Sisemisi omahinna komponente ei kuvata.
