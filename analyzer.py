"""
Vinted Telefon Analyzer — Gemini AI elemzés
============================================
Beolvassa a scraper.py által generált data/results.json-t,
kiszűri a top 10 valódi telefont minimumár szűrővel (tokok kiesnek),
lekéri a részletes leírást a Vinted API-ból,
majd Gemini AI-val értékeli melyik a legjobb deal.

Szükséges:
    pip install vinted-scraper google-generativeai

Gemini API kulcs beállítása:
    GitHub → Settings → Secrets and variables → Actions → Variables → GEMINI_API_KEY
    (ingyenes: aistudio.google.com/app/apikey)
"""

import json
import os
import time
from pathlib import Path

try:
    from vinted_scraper import VintedScraper
except ImportError:
    raise SystemExit("Hiányzó csomag! Futtasd: pip install vinted-scraper")

try:
    import google.generativeai as genai
except ImportError:
    raise SystemExit("Hiányzó csomag! Futtasd: pip install google-generativeai")


# ── Beállítások ────────────────────────────────────────────────────────────────

BASE_URL    = "https://www.vinted.hu"
INPUT_FILE  = Path("data/results.json")
OUTPUT_FILE = Path("data/analysis.md")
TOP_N       = 10

# ── Minimumár modellenkénti szűrő ─────────────────────────────────────────────
# Ha egy "iPhone 15 Pro Max" 8000 Ft-ért szerepel, az biztosan tok.
# Az alábbi értékek az adott modell legalacsonyabb REÁLIS ára Ft-ban.

MINIMUM_ARAK = {
    "iphone 15 pro max": 200000,
    "iphone 15 pro":     170000,
    "iphone 15 plus":    150000,
    "iphone 15":         130000,
    "iphone 14 pro max": 150000,
    "iphone 14 pro":     120000,
    "iphone 14 plus":    100000,
    "iphone 14":          90000,
    "iphone 13 pro max": 110000,
    "iphone 13 pro":      90000,
    "iphone 13":          60000,
    "iphone 13 mini":     50000,
    "iphone 12 pro max":  75000,
    "iphone 12 pro":      60000,
    "iphone 12":          40000,
    "iphone 12 mini":     35000,
    "iphone 11":          30000,
    "samsung s24 ultra":  180000,
    "samsung s24+":       140000,
    "samsung s24":        110000,
    "samsung s23 ultra":  130000,
    "samsung s23+":        95000,
    "samsung s23":         70000,
    "samsung s22 ultra":   90000,
    "samsung s22+":        65000,
    "samsung s22":         50000,
    "samsung a54":         40000,
    "samsung a53":         30000,
    "pixel 8 pro":        110000,
    "pixel 8":             80000,
    "pixel 7 pro":         80000,
    "pixel 7":             55000,
    "xiaomi 13":           55000,
    "xiaomi 12":           40000,
    "poco x5 pro":         35000,
    "poco x5":             25000,
    "oneplus 11":          65000,
    "motorola edge 40 pro": 55000,
}

# ── Szöveges kiszűrők ─────────────────────────────────────────────────────────
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


def is_valodi_telefon(item: dict) -> tuple[bool, str]:
    cim = item["cim"].lower()
    modell = item.get("azonositott_modell")
    ar = item.get("ar_ft", 0)

    for szo in TOK_SZAVAK:
        if szo in cim:
            return False, f"tok kulcsszo: '{szo}'"

    if modell and modell in MINIMUM_ARAK:
        min_ar = MINIMUM_ARAK[modell]
        if ar < min_ar:
            return False, f"ar ({ar:.0f} Ft) < minimum ({min_ar:.0f} Ft)"

    return True, ""


def load_results() -> list[dict]:
    if not INPUT_FILE.exists():
        raise SystemExit(f"Nem talalhato: {INPUT_FILE} — futtasd elobb a scraper.py-t!")
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"  Beolvasva: {len(data)} db termek")
    return data


def get_top_phones(data: list[dict], n: int) -> list[dict]:
    valodiak = []
    kiszurve = 0

    for item in data:
        if not item.get("azonositott_modell"):
            continue
        megfelel, ok = is_valodi_telefon(item)
        if megfelel:
            valodiak.append(item)
        else:
            kiszurve += 1

    print(f"  Kiszurve (tok/minimum ar): {kiszurve} db")
    print(f"  Valodi telefonok: {len(valodiak)} db")

    top = valodiak[:n]
    print(f"  Kivalasztva elemzesre: {len(top)} db")
    for i, t in enumerate(top, 1):
        print(f"    {i}. {t['cim'][:50]} — {t['ar_ft']:,.0f} Ft ({t['allapot']})")
    print()
    return top


def fetch_description(scraper: VintedScraper, item_id: int) -> str:
    try:
        detail = scraper.item(item_id)
        desc = getattr(detail, "description", "") or ""
        return str(desc).strip()[:800]
    except Exception as e:
        return f"[Leiras nem elerheto: {e}]"


def enrich_with_descriptions(scraper: VintedScraper, phones: list[dict]) -> list[dict]:
    print("  Reszletes leirasok lekerdezese...")
    for i, phone in enumerate(phones, 1):
        item_id = phone.get("id")
        print(f"    {i}/{len(phones)}: {phone['cim'][:45]} ...", end="", flush=True)
        if item_id:
            desc = fetch_description(scraper, item_id)
            phone["leiras_teljes"] = desc
            print(f" {len(desc)} karakter")
        else:
            phone["leiras_teljes"] = ""
            print(" nincs ID")
        time.sleep(1.2)
    return phones


def format_for_ai(phones: list[dict]) -> str:
    lines = []
    for i, p in enumerate(phones, 1):
        piaci = p.get("piaci_referenciar")
        piaci_str = f"{piaci:,.0f} Ft" if piaci else "ismeretlen"
        lines.append(
            f"--- TELEFON #{i} ---\n"
            f"Cim: {p['cim']}\n"
            f"Ar: {p['ar_ft']:,.0f} Ft\n"
            f"Piaci referencia ar: {piaci_str}\n"
            f"A piaci ar szazaleka: {p['arErtek_piaci_szazalek']}%\n"
            f"Allapot: {p['allapot']}\n"
            f"Elado ertekeles: {p['ertekeles']}/5.0 ({p['ertekeles_db']} ertekeles)\n"
            f"Leiras: {p.get('leiras_teljes') or '(nincs leiras)'}\n"
            f"Link: {p['url']}\n"
        )
    return "\n".join(lines)


def analyze_with_gemini(phones: list[dict]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit(
            "Hianyzo API kulcs!\n"
            "GitHub: Settings > Secrets and variables > Actions > Variables > GEMINI_API_KEY\n"
            "Helyi: export GEMINI_API_KEY=AIza..."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    telefon_adatok = format_for_ai(phones)

    prompt = f"""Te egy tapasztalt okostelefon-szakerto vagy, aki segit megtalalni a legjobb ar-ertek aranyú hasznalt telefont a Vinted piacteren.

Az alabbiakban a jelenleg elerheto legjobb ajanaltok listaja. A piaci ar szazaleka azt mutatja, hany szazaleka az adott ar a tipikus hasznalt bolti arnak — minel alacsonyabb, annal jobb deal.

{telefon_adatok}

Kerem, elemezd ezeket az ajanlaltokat es:

1. Jelold meg a TOP 3 legjobb dealt (indokold: ar, allapot, elado megbizhatosaga alapjan)
2. Hivd fel figyelmet ha valamelyik gyanussan olcso vagy a leiras alapjan problemás
3. Adj rovid altalanos tanácsot mire figyeljen a vevo vásárlás elott

Valaszolj magyarul, kozerthetoen. Legy konkret — irj arakat es modellneveket.
"""

    print("\n  Gemini AI elemzes folyamatban...")
    response = model.generate_content(prompt)
    return response.text


def save_analysis(phones: list[dict], ai_text: str) -> None:
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Vinted Telefon Elemzes — {now}\n",
        "## Gemini AI velemenye\n",
        ai_text,
        "\n---\n",
        "## Elemzett termekek\n",
    ]
    for i, p in enumerate(phones, 1):
        piaci = p.get("piaci_referenciar")
        lines.append(
            f"### #{i} — {p['cim']}\n"
            f"- **Ar:** {p['ar_ft']:,.0f} Ft"
            + (f" (piaci ref: {piaci:,.0f} Ft — **{p['arErtek_piaci_szazalek']}%**)" if piaci else "")
            + f"\n- **Allapot:** {p['allapot']}\n"
            f"- **Elado:** {p['elado']} — {p['ertekeles']}/5 ({p['ertekeles_db']} ertekeles)\n"
            f"- **Link:** {p['url']}\n"
            f"- **Leiras:** {p.get('leiras_teljes') or '(nincs)'}\n"
        )

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Mentve: {OUTPUT_FILE}")


def main():
    print("=" * 65)
    print("  Vinted Telefon Analyzer — Gemini AI elemzes")
    print("=" * 65)

    data  = load_results()
    top10 = get_top_phones(data, TOP_N)

    if not top10:
        print("\n  Nincs elegendo valodi telefon az elemzeshez.")
        print("  Ellenorizd a MINIMUM_ARAK ertekeket az analyzer.py-ban.")
        return

    scraper = VintedScraper(BASE_URL)
    top10   = enrich_with_descriptions(scraper, top10)

    ai_szoveg = analyze_with_gemini(top10)
    save_analysis(top10, ai_szoveg)

    print("\n" + "=" * 65)
    print("  GEMINI AI ELEMZES EREDMENYE")
    print("=" * 65)
    print(ai_szoveg)
    print(f"\n  Reszletes riport: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
