"""
Vinted Telefon Kereső — Streamlit UI
=====================================
Streamlit Cloud-on fut ingyenesen.
Deploy: streamlit.io/cloud -> GitHub repo -> app.py

Szükséges environment variable (Streamlit Cloud -> Settings -> Secrets):
    GEMINI_API_KEY = "AIza..."
"""

import json
import os
import time
import sys
from pathlib import Path

import streamlit as st

# ── Oldal beállítások ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vinted Telefon Kereső",
    page_icon="📱",
    layout="wide",
)

# ── Függőség ellenőrzés ───────────────────────────────────────────────────────
try:
    from vinted_scraper import VintedScraper
except ImportError:
    st.error("Hiányzó csomag: vinted-scraper. Ellenőrizd a requirements.txt fájlt.")
    st.stop()

try:
    from google import genai
    GEMINI_OK = True
except ImportError:
    GEMINI_OK = False

# ── Konstansok ────────────────────────────────────────────────────────────────
BASE_URL = "https://www.vinted.hu"

TELEFON_MODELLEK = [
    "iphone 15 pro max", "iphone 15 pro", "iphone 15",
    "iphone 14 pro max", "iphone 14 pro", "iphone 14",
    "iphone 13 pro", "iphone 13", "iphone 13 mini",
    "iphone 12 pro", "iphone 12", "iphone 12 mini",
    "iphone 11",
    "samsung s24 ultra", "samsung s24", "samsung s23 ultra", "samsung s23",
    "samsung s22 ultra", "samsung s22", "samsung a54", "samsung a53",
    "pixel 8 pro", "pixel 8", "pixel 7 pro", "pixel 7",
    "xiaomi 13", "xiaomi 12",
    "poco x5 pro", "poco x5",
    "oneplus 11",
    "motorola edge 40 pro",
]

PIACI_ARAK = {
    "iphone 15 pro max": 420000, "iphone 15 pro": 360000,
    "iphone 15 plus": 310000,    "iphone 15": 270000,
    "iphone 14 pro max": 340000, "iphone 14 pro": 280000,
    "iphone 14 plus": 230000,    "iphone 14": 200000,
    "iphone 13 pro max": 260000, "iphone 13 pro": 210000,
    "iphone 13": 160000,         "iphone 13 mini": 130000,
    "iphone 12 pro max": 190000, "iphone 12 pro": 150000,
    "iphone 12": 110000,         "iphone 12 mini": 90000,
    "iphone 11": 75000,
    "samsung s24 ultra": 380000, "samsung s24+": 280000,
    "samsung s24": 220000,       "samsung s23 ultra": 300000,
    "samsung s23+": 220000,      "samsung s23": 170000,
    "samsung s22 ultra": 230000, "samsung s22+": 170000,
    "samsung s22": 130000,       "samsung a54": 100000,
    "samsung a53": 80000,
    "pixel 8 pro": 260000,       "pixel 8": 190000,
    "pixel 7 pro": 200000,       "pixel 7": 140000,
    "xiaomi 13": 140000,         "xiaomi 12": 100000,
    "poco x5 pro": 90000,        "poco x5": 70000,
    "oneplus 11": 160000,        "motorola edge 40 pro": 140000,
}

MINIMUM_ARAK = {
    "iphone 15 pro max": 200000, "iphone 15 pro": 170000,
    "iphone 15 plus": 150000,    "iphone 15": 130000,
    "iphone 14 pro max": 150000, "iphone 14 pro": 120000,
    "iphone 14 plus": 100000,    "iphone 14": 90000,
    "iphone 13 pro max": 110000, "iphone 13 pro": 90000,
    "iphone 13": 60000,          "iphone 13 mini": 50000,
    "iphone 12 pro max": 75000,  "iphone 12 pro": 60000,
    "iphone 12": 40000,          "iphone 12 mini": 35000,
    "iphone 11": 30000,
    "samsung s24 ultra": 180000, "samsung s24+": 140000,
    "samsung s24": 110000,       "samsung s23 ultra": 130000,
    "samsung s23+": 95000,       "samsung s23": 70000,
    "samsung s22 ultra": 90000,  "samsung s22+": 65000,
    "samsung s22": 50000,        "samsung a54": 40000,
    "samsung a53": 30000,
    "pixel 8 pro": 110000,       "pixel 8": 80000,
    "pixel 7 pro": 80000,        "pixel 7": 55000,
    "xiaomi 13": 55000,          "xiaomi 12": 40000,
    "poco x5 pro": 35000,        "poco x5": 25000,
    "oneplus 11": 65000,         "motorola edge 40 pro": 55000,
}

CONDITION_MAP = {1: "Új", 2: "Kiváló", 3: "Jó", 4: "Megfelelő"}

TOK_SZAVAK = [
    "tok ", " tok", "tokot", "telefontok",
    "case", "cover", "etui", "husa", "husă", "coque", "funda",
    "pokrowiec", "obal", "kryt", "schutzhülle", "hoesje", "skal",
    "kijelzővédő", "üvegfólia", "folie", "screen protector",
    "charger", "töltő", "cable", "kábel", "strap", "szíj",
    "earphone", "fülhallgató", "headphone", "airpods",
    "hangszóró", "speaker",
    "pentru piese", "na części", "for parts", "alkatrész",
    "zamienię", "ładowarka", "ladowarka",
]

FUNKCIOK_CONFIG = {
    "NFC": ["nfc"],
    "Wireless töltés": ["wireless", "qi töltés", "magsafe", "wireless charging", "vezeték nélküli töltés"],
    "5G": ["5g"],
}


# ── Segédfüggvények ───────────────────────────────────────────────────────────

def azonosit_modellt(cim: str):
    c = cim.lower()
    for m in sorted(PIACI_ARAK.keys(), key=len, reverse=True):
        if m in c:
            return m
    return None


def is_valodi_telefon(cim: str, ar: float, modell):
    c = cim.lower()
    for szo in TOK_SZAVAK:
        if szo in c:
            return False
    if modell and modell in MINIMUM_ARAK:
        if ar < MINIMUM_ARAK[modell]:
            return False
    return True


def teljesiti_funkciokat(cim: str, leiras: str, kivalasztott_funkciok: list) -> bool:
    szoveg = (cim + " " + leiras).lower()
    for funk in kivalasztott_funkciok:
        kulcsszavak = FUNKCIOK_CONFIG.get(funk, [])
        if not any(kw in szoveg for kw in kulcsszavak):
            return False
    return True


def pontszam(ar, modell, allapot_id, rating, feedback_db) -> float:
    piaci = PIACI_ARAK.get(modell) if modell else None
    alap = (ar / piaci * 100) if piaci else 100.0
    szorzo = {1: 0.88, 2: 0.93, 3: 1.00, 4: 1.12}.get(int(allapot_id or 3), 1.0)
    bonus = (rating / 5.0 * 0.05) if feedback_db >= 10 else (rating / 5.0 * 0.02) if feedback_db >= 3 else 0
    return round(alap * szorzo * (1 - bonus), 2)


def parse_item(raw, query, allapot_szurok, funkciok, min_ar, max_ar):
    cim = str(getattr(raw, "title", "") or "")
    leiras = str(getattr(raw, "description", "") or "")

    cond_id = getattr(raw, "status_id", None) or getattr(raw, "condition_id", None)
    try:
        cond_int = int(cond_id)
    except:
        cond_int = 3
    if cond_int not in allapot_szurok:
        return None

    try:
        ar = float(str(getattr(raw, "price", 0)).replace(",", ".").replace(" ", ""))
    except:
        return None
    if ar < min_ar or ar > max_ar:
        return None

    modell = azonosit_modellt(cim)
    if not modell:
        return None

    if not is_valodi_telefon(cim, ar, modell):
        return None

    if funkciok and not teljesiti_funkciokat(cim, leiras, funkciok):
        return None

    user = getattr(raw, "user", None)
    rating = float(getattr(user, "feedback_reputation", 0) or 0) if user else 0.0
    fb_db = int(getattr(user, "positive_feedback_count", 0) or 0) if user else 0
    seller = getattr(user, "login", "?") if user else "?"

    photo = getattr(raw, "photo", None)
    kep = photo.get("url", "") if isinstance(photo, dict) else str(photo or "")

    piaci = PIACI_ARAK.get(modell)
    piaci_pct = round((ar / piaci * 100), 1) if piaci else None

    return {
        "id": getattr(raw, "id", None),
        "cim": cim,
        "ar_ft": ar,
        "allapot": CONDITION_MAP.get(cond_int, "?"),
        "allapot_id": cond_int,
        "elado": seller,
        "ertekeles": round(rating, 1),
        "ertekeles_db": fb_db,
        "modell": modell,
        "piaci_ar": piaci,
        "piaci_pct": piaci_pct,
        "url": getattr(raw, "url", ""),
        "kep": kep,
        "kereses": query,
        "pont": pontszam(ar, modell, cond_int, rating, fb_db),
    }


@st.cache_data(ttl=1800, show_spinner=False)
def scrape_phones(modellek, allapot_ids, funkciok, min_ar, max_ar, top_n):
    scraper = VintedScraper(BASE_URL)
    osszes = []
    seen = set()

    for query in modellek:
        try:
            raw_items = scraper.search({
                "search_text": query,
                "order": "newest_first",
                "per_page": 96,
                "price_from": min_ar,
                "price_to": max_ar,
            })
        except Exception as e:
            st.warning(f"Hiba a '{query}' keresésnél: {e}")
            continue

        for raw in raw_items:
            item = parse_item(raw, query, set(allapot_ids), funkciok, min_ar, max_ar)
            if item and item["id"] not in seen:
                seen.add(item["id"])
                osszes.append(item)
        time.sleep(1.0)

    rendezett = sorted(osszes, key=lambda x: x["pont"])
    return rendezett[:top_n]


def gemini_elemzes(phones: list) -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return "❌ Nincs GEMINI_API_KEY beállítva (Streamlit Cloud → Settings → Secrets)."
    if not GEMINI_OK:
        return "❌ google-genai csomag hiányzik."

    client = genai.Client(api_key=api_key)
    sorok = []
    for i, p in enumerate(phones, 1):
        piaci_str = f"{p['piaci_ar']:,.0f} Ft ({p['piaci_pct']}%)" if p["piaci_ar"] else "ismeretlen"
        sorok.append(
            f"#{i} {p['cim']} | {p['ar_ft']:,.0f} Ft | piaci: {piaci_str} | "
            f"{p['allapot']} | {p['ertekeles']}/5 ({p['ertekeles_db']} értékelés) | {p['url']}"
        )

    prompt = (
        "Te egy okostelefon-szakértő vagy. Az alábbi Vinted hirdetések a legjobb ár-érték arányúak "
        "(piaci ár %-a alapján rendezve, alacsonyabb = jobb).\n\n"
        + "\n".join(sorok)
        + "\n\nEmeld ki a TOP 3 legjobb dealt rövid indoklással. "
        "Jelezd ha valami gyanús. Válaszolj magyarul, tömören."
    )

    for attempt in range(3):
        try:
            resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return resp.text
        except Exception as e:
            if "429" in str(e) or "EXHAUSTED" in str(e):
                wait = 20 * (attempt + 1)
                time.sleep(wait)
            else:
                return f"❌ Gemini hiba: {e}"
    return "❌ Gemini rate limit — próbáld újra pár perc múlva."


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("📱 Vinted Telefon Kereső")
st.caption("Automatikusan gyűjti és ár-érték szerint rangsorolja a Vinted.hu telefon hirdetéseit.")

# Sidebar — szűrők
with st.sidebar:
    st.header("⚙️ Szűrők")

    st.subheader("Keresett modellek")
    kivalasztott_modellek = st.multiselect(
        "Melyik modelleket keressen?",
        options=TELEFON_MODELLEK,
        default=["iphone 13", "iphone 12", "samsung s23", "pixel 7"],
        help="Tartsd lenyomva Ctrl/Cmd-et több kiválasztáshoz",
    )

    st.subheader("Ár tartomány")
    min_ar, max_ar = st.slider(
        "Ár (Ft)",
        min_value=5000,
        max_value=300000,
        value=(20000, 150000),
        step=5000,
        format="%d Ft",
    )

    st.subheader("Állapot")
    uj = st.checkbox("Új", value=False)
    kivalo = st.checkbox("Kiváló", value=True)
    jo = st.checkbox("Jó", value=True)
    megfelelo = st.checkbox("Megfelelő", value=False)

    allapot_ids = []
    if uj: allapot_ids.append(1)
    if kivalo: allapot_ids.append(2)
    if jo: allapot_ids.append(3)
    if megfelelo: allapot_ids.append(4)
    if not allapot_ids:
        allapot_ids = [2, 3]

    st.subheader("Funkciók")
    funk_nfc = st.checkbox("NFC", value=False)
    funk_wireless = st.checkbox("Wireless töltés", value=False)
    funk_5g = st.checkbox("5G", value=False)

    kivalasztott_funkciok = []
    if funk_nfc: kivalasztott_funkciok.append("NFC")
    if funk_wireless: kivalasztott_funkciok.append("Wireless töltés")
    if funk_5g: kivalasztott_funkciok.append("5G")

    st.subheader("Találatok")
    top_n = st.slider("Legjobb hány találatot mutasson?", 5, 30, 10)

    st.subheader("AI elemzés")
    ai_be = st.checkbox("Gemini AI elemzés bekapcsolva", value=True)

    st.divider()
    kereses_gomb = st.button("🔍 Keresés indítása", type="primary", use_container_width=True)

# Főoldal
if not kereses_gomb:
    st.info("👈 Állítsd be a szűrőket a bal oldali panelen, majd kattints a **Keresés indítása** gombra.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Elérhető modellek", len(TELEFON_MODELLEK))
    with col2:
        st.metric("Piaci referencia adatok", len(PIACI_ARAK))
    with col3:
        st.metric("Szűrhető funkciók", len(FUNKCIOK_CONFIG))
    st.stop()

if not kivalasztott_modellek:
    st.warning("Válassz ki legalább egy modellt a bal oldali panelen!")
    st.stop()

# Keresés futtatása
with st.spinner(f"🔍 Keresés: {len(kivalasztott_modellek)} modell, {min_ar:,}–{max_ar:,} Ft..."):
    eredmenyek = scrape_phones(
        tuple(kivalasztott_modellek),
        tuple(sorted(allapot_ids)),
        tuple(kivalasztott_funkciok),
        min_ar,
        max_ar,
        top_n,
    )

if not eredmenyek:
    st.warning("Nem találtam találatot ezekkel a szűrőkkel. Próbálj szélesebb ár tartományt vagy más modelleket.")
    st.stop()

st.success(f"✅ {len(eredmenyek)} találat (szűrve, ár-érték szerint rendezve)")

# Eredmény táblázat
st.subheader("📊 Találatok")

tabla_adatok = []
for i, p in enumerate(eredmenyek, 1):
    piaci_str = f"{p['piaci_pct']}%" if p["piaci_pct"] else "—"
    csillag = "★" * round(p["ertekeles"]) + "☆" * (5 - round(p["ertekeles"]))
    tabla_adatok.append({
        "#": i,
        "Modell": p["modell"] or p["cim"][:30],
        "Cím": p["cim"][:45],
        "Ár (Ft)": f"{p['ar_ft']:,.0f}",
        "Piaci ár %": piaci_str,
        "Állapot": p["allapot"],
        "Értékelés": f"{csillag} ({p['ertekeles_db']})",
        "Link": p["url"],
    })

import pandas as pd
df = pd.DataFrame(tabla_adatok)
st.dataframe(
    df,
    column_config={
        "Link": st.column_config.LinkColumn("Link", display_text="🔗 Megnyit"),
        "Piaci ár %": st.column_config.TextColumn("Piaci ár %", help="Hány %-a a szokásos piaci árnak (alacsonyabb = jobb deal)"),
    },
    hide_index=True,
    use_container_width=True,
)

# Top 3 kártyák
st.subheader("🏆 Top 3 kiemelve")
cols = st.columns(min(3, len(eredmenyek)))
for i, col in enumerate(cols):
    p = eredmenyek[i]
    with col:
        piaci_str = f"Piaci ár {p['piaci_pct']}%-a" if p["piaci_pct"] else ""
        megtakaritas = ""
        if p["piaci_ar"] and p["ar_ft"]:
            meg = p["piaci_ar"] - p["ar_ft"]
            if meg > 0:
                megtakaritas = f"~{meg:,.0f} Ft megtakarítás"

        st.markdown(f"""
**#{i+1} {p['modell'].title() if p['modell'] else p['cim'][:25]}**

💰 **{p['ar_ft']:,.0f} Ft**
{f"📉 {piaci_str}" if piaci_str else ""}
{f"💚 {megtakaritas}" if megtakaritas else ""}

📦 {p['allapot']} állapot
⭐ {p['ertekeles']}/5 ({p['ertekeles_db']} értékelés)

[🔗 Megnézem Vinteden]({p['url']})
""")

# AI elemzés
if ai_be:
    st.subheader("🤖 Gemini AI elemzés")
    with st.spinner("Gemini elemzi a találatokat..."):
        ai_szoveg = gemini_elemzes(eredmenyek[:10])
    st.markdown(ai_szoveg)

# Nyers adatok
with st.expander("🗂️ Összes adat (JSON)"):
    st.json(eredmenyek)
