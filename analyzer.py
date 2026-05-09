"""
Vinted Telefon Analyzer — Claude AI elemzés
============================================
Beolvassa a scraper.py által generált data/results.json-t,
kiszűri a top 10 valódi telefont (tokok, kiegészítők nélkül),
lekéri a részletes leírást a Vinted API-ból,
majd Claude AI-val értékeli melyik a legjobb deal.

Szükséges:
    pip install vinted-scraper anthropic

Anthropic API kulcs beállítása (egyszer kell):
    GitHub → Settings → Secrets → Actions → New secret
    Név: ANTHROPIC_API_KEY
    Érték: sk-ant-...  (https://console.anthropic.com/settings/keys)
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
    import anthropic
except ImportError:
    raise SystemExit("Hiányzó csomag! Futtasd: pip install anthropic")


# ── Beállítások ────────────────────────────────────────────────────────────────

BASE_URL       = "https://www.vinted.hu"
INPUT_FILE     = Path("data/results.json")
OUTPUT_FILE    = Path("data/analysis.md")
TOP_N          = 10    # hány telefont elemezzen az AI

# Kiszűrendő szavak — ezek NEM valódi telefonok
TOK_SZAVAK = [
    "tok", "case", "cover", "etui", "husa", "husă", "coque", "funda",
    "pokrowiec", "obal", "kryt", "schutzhülle", "hoesje", "skal",
    "θήκ", "kijelzővédő", "üvegfólia", "folie", "screen protector",
    "charger", "töltő", "cable", "kábel", "strap", "szíj",
    "earphone", "fülhallgató", "headphone", "airpods",
    "soundbar", "hangszóró", "speaker",
    "pentru piese", "na części", "for parts", "alkatrész",   # törött/alkatrész
    "zamienię", "csere", "exchange",                          # csere ajánlatok
    "ładowarka", "ladowarka",                                 # töltő lengyelül
]


def is_valodi_telefon(cim: str) -> bool:
    """True ha valódi telefon (nem tok, nem kiegészítő, nem törött alkatrész)."""
    c = cim.lower()
    return not any(t in c for t in TOK_SZAVAK)


def load_results() -> list[dict]:
    """Beolvassa a scraper eredményeit."""
    if not INPUT_FILE.exists():
        raise SystemExit(f"Nem található: {INPUT_FILE} — futtasd előbb a scraper.py-t!")
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"  Beolvasva: {len(data)} db termék a {INPUT_FILE} fájlból")
    return data


def get_top_phones(data: list[dict], n: int) -> list[dict]:
    """
    Kiszűri a valódi telefonokat (azonosított modellel),
    majd visszaadja a legjobb n db-ot pontszám szerint.
    """
    valodiak = [
        d for d in data
        if d.get("azonositott_modell")       # ismert modell
        and is_valodi_telefon(d["cim"])       # nem tok/kiegészítő
    ]
    print(f"  Valódi telefon (tok/kiegészítő szűrés után): {len(valodiak)} db")
    top = valodiak[:n]
    print(f"  Kiválasztva elemzésre: {len(top)} db\n")
    return top


def fetch_description(scraper: VintedScraper, item_id: int) -> str:
    """
    Lekéri egy termék részletes leírását a Vinted API-ból.
    A keresési lista nem tartalmazza a leírást — ezt külön kell lekérni.
    """
    try:
        detail = scraper.item(item_id)
        desc = getattr(detail, "description", "") or ""
        return str(desc).strip()[:600]   # max 600 karakter, hogy ne legyen túl hosszú
    except Exception as e:
        return f"[Leírás nem elérhető: {e}]"


def enrich_with_descriptions(scraper: VintedScraper, phones: list[dict]) -> list[dict]:
    """Minden telefonhoz lekéri a részletes leírást."""
    print("  Részletes leírások lekérése (egyenként)...")
    for i, phone in enumerate(phones, 1):
        item_id = phone.get("id")
        print(f"    {i}/{len(phones)}: {phone['cim'][:45]} ...", end="", flush=True)
        if item_id:
            desc = fetch_description(scraper, item_id)
            phone["leiras_teljes"] = desc
            print(f" ({len(desc)} karakter)")
        else:
            phone["leiras_teljes"] = ""
            print(" (nincs ID)")
        time.sleep(1.2)   # udvarias szünet
    return phones


def format_for_ai(phones: list[dict]) -> str:
    """Összefoglaló szöveget készít a Claude AI számára."""
    lines = []
    for i, p in enumerate(phones, 1):
        piaci = p.get("piaci_referenciar")
        piaci_str = f"{piaci:,.0f} Ft" if piaci else "ismeretlen"
        lines.append(f"""
--- TELEFON #{i} ---
Cím: {p['cim']}
Ár: {p['ar_ft']:,.0f} Ft
Piaci referencia ár (használt bolti átlag): {piaci_str}
Állapot: {p['allapot']}
Eladó értékelése: {p['ertekeles']}/5.0 ({p['ertekeles_db']} értékelés)
Ár-érték pontszám (alacsonyabb = jobb): {p.get('arErtek_pontszam', '?')}
Piaci ár %-a: {p['arErtek_piaci_szazalek']}%
Leírás: {p.get('leiras_teljes') or '(nincs leírás)'}
Link: {p['url']}
""")
    return "\n".join(lines)


def analyze_with_claude(phones: list[dict]) -> str:
    """Claude AI-val elemzi a top telefonokat és megmondja melyik a legjobb deal."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "Hiányzó API kulcs!\n"
            "GitHub Actions: Settings → Secrets → Actions → ANTHROPIC_API_KEY\n"
            "Helyi futtatás: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic(api_key=api_key)
    telefon_adatok = format_for_ai(phones)

    prompt = f"""Te egy tapasztalt okostelefon-szakértő vagy, aki segít megtalálni a legjobb ár-érték arányú használt telefont a Vinted piacterén.

Az alábbiakban a jelenleg elérhető legjobb ajánlatok listája látható, amelyeket egy automatikus rendszer gyűjtött össze és előszűrt. Az "ár-érték pontszám" azt mutatja, hány %-a az adott ár a tipikus használt bolti árnak — minél alacsonyabb, annál jobb deal.

{telefon_adatok}

Kérlek, elemezd ezeket az ajánlatokat és:

1. **Jelöld meg a TOP 3 legjobb dealt** (indokold meg miért)
2. **Hívj fel figyelmet** ha valamelyik gyanúsan olcsó (esetleg sérült, alkatrésznek szánt, vagy a leírás alapján problémás)
3. **Adj általános tanácsot** mire figyeljen a vevő mielőtt megveszi

Válaszolj magyarul, közérthetően. Legyél konkrét — írj árakat, modellneveket.
"""

    print("\n  Claude AI elemzés folyamatban...")
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def save_analysis(phones: list[dict], ai_text: str) -> None:
    """Elmenti az elemzést Markdown fájlba."""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Vinted Telefon Elemzés — {now}\n",
        "## Claude AI véleménye\n",
        ai_text,
        "\n---\n",
        "## Elemzett termékek részletei\n",
    ]

    for i, p in enumerate(phones, 1):
        piaci = p.get("piaci_referenciar")
        lines.append(
            f"### #{i} — {p['cim']}\n"
            f"- **Ár:** {p['ar_ft']:,.0f} Ft"
            + (f" (piaci ref: {piaci:,.0f} Ft, **{p['arErtek_piaci_szazalek']}%**)" if piaci else "")
            + f"\n- **Állapot:** {p['allapot']}\n"
            f"- **Eladó:** {p['elado']} — {p['ertekeles']}/5.0 ({p['ertekeles_db']} értékelés)\n"
            f"- **Link:** {p['url']}\n"
            f"- **Leírás:** {p.get('leiras_teljes') or '(nincs)'}\n"
        )

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Mentve: {OUTPUT_FILE}")


def main():
    print("=" * 65)
    print("  Vinted Telefon Analyzer — Claude AI elemzés")
    print("=" * 65)

    # 1. Adatok betöltése
    data   = load_results()
    top10  = get_top_phones(data, TOP_N)

    # 2. Részletes leírások lekérése
    scraper = VintedScraper(BASE_URL)
    top10   = enrich_with_descriptions(scraper, top10)

    # 3. AI elemzés
    ai_szoveg = analyze_with_claude(top10)

    # 4. Mentés + kiírás
    save_analysis(top10, ai_szoveg)

    print("\n" + "=" * 65)
    print("  CLAUDE AI ELEMZÉS EREDMÉNYE")
    print("=" * 65)
    print(ai_szoveg)
    print("\n  Részletes riport: data/analysis.md")


if __name__ == "__main__":
    main()
