"""
Vinted Telefon Ár-Érték Scraper
================================
Összegyűjti a Vinted-ről az összes használt telefont,
szűri funkciók alapján (NFC, wireless charging, stb.),
és ár-érték szerint rangsorolja őket.

Referencia árak: átlagos piaci ár (pl. használt bolt ár)
alapján értékeli hogy olcsó-e az adott ajánlat.
"""

import json
import time
import datetime
from pathlib import Path

try:
    from vinted_scraper import VintedScraper
except ImportError:
    raise SystemExit("Hiányzó csomag! Futtasd: pip install vinted-scraper")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  BEÁLLÍTÁSOK — itt módosítsd a keresési paramétereket                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

BASE_URL    = "https://www.vinted.hu"
DATA_DIR    = Path("data")
OUTPUT_FILE = DATA_DIR / "results.json"

# ── Ár szűrők (Ft) ────────────────────────────────────────────────────────────
MIN_PRICE = 8_000
MAX_PRICE = 200_000

# ── Állapot szűrők ────────────────────────────────────────────────────────────
# 1=Új  2=Kiváló  3=Jó  4=Megfelelő  (6=Gyűjthető — kihagyjuk)
ACCEPTED_CONDITION_IDS = {1, 2, 3}

# ── Eladói megbízhatóság ──────────────────────────────────────────────────────
MIN_SELLER_RATING      = 3.5   # 0–5 skálán
MIN_SELLER_FEEDBACKS   = 3     # ennyi értékelés alatt nem szűrünk (új eladó)

# ── Keresési kifejezések ──────────────────────────────────────────────────────
# Minél általánosabb → több találat, de több zaj is
SEARCH_QUERIES = [
    "iphone 13",
    "iphone 14",
    "iphone 12",
    "iphone 15",
    "samsung s23",
    "samsung s22",
    "samsung a54",
    "samsung a53",
    "pixel 7",
    "pixel 8",
    "xiaomi 12",
    "poco x5",
    "oneplus 11",
    "motorola edge",
]

# ── Funkció szűrők ────────────────────────────────────────────────────────────
# Állítsd True/False értékre hogy aktív-e az adott szűrő.
# A szűrők a termék NEVÉBŐL és LEÍRÁSÁBÓL dolgoznak (mert a Vinted nem
# ad külön spec mezőket), ezért kulcsszavakra támaszkodunk.
#
# Ha nem akarsz szűrni semmire → mindent False-ra állíts.

FUNKCIOK = {
    "nfc": {
        "aktiv": False,           # csak NFC-s telefonokat listázzon?
        "kulcsszavak": ["nfc"],
        "nem_tartalmaz": [],      # ezeket NE tartalmazza a leírás
    },
    "wireless_charging": {
        "aktiv": False,           # csak wireless charging-es modelleket?
        "kulcsszavak": [
            "wireless", "vezeték nélküli töltés", "qi töltés",
            "magsafe", "wireless charging",
        ],
        "nem_tartalmaz": [],
    },
    "5g": {
        "aktiv": False,
        "kulcsszavak": ["5g"],
        "nem_tartalmaz": [],
    },
    "esallapot": {
        "aktiv": False,           # csak ép kijelzős (nem repedezett)?
        "kulcsszavak": [],
        "nem_tartalmaz": [
            "törött", "repedt", "sérült kijelző", "crack",
            "broken screen", "hibás", "nem működik",
        ],
    },
}

# ── Piaci referencia árak (Ft) ─────────────────────────────────────────────────
# Ezek HOZZÁVETŐLEGES átlagos használt bolti/piaci árak.
# Az "ár-érték pontszám" ehhez viszonyít.
# Ha egy modell nincs a listában, az általános logika fut le.
#
# Forrás: mobilarena.hu, gsmarena használt árak, 2025 eleje
PIACI_ARAK = {
    "iphone 15 pro max": 420_000,
    "iphone 15 pro":     360_000,
    "iphone 15 plus":    310_000,
    "iphone 15":         270_000,
    "iphone 14 pro max": 340_000,
    "iphone 14 pro":     280_000,
    "iphone 14 plus":    230_000,
    "iphone 14":         200_000,
    "iphone 13 pro max": 260_000,
    "iphone 13 pro":     210_000,
    "iphone 13":         160_000,
    "iphone 13 mini":    130_000,
    "iphone 12 pro max": 190_000,
    "iphone 12 pro":     150_000,
    "iphone 12":         110_000,
    "iphone 12 mini":     90_000,
    "iphone 11":          75_000,
    "samsung s24 ultra":  380_000,
    "samsung s24+":       280_000,
    "samsung s24":        220_000,
    "samsung s23 ultra":  300_000,
    "samsung s23+":       220_000,
    "samsung s23":        170_000,
    "samsung s22 ultra":  230_000,
    "samsung s22+":       170_000,
    "samsung s22":        130_000,
    "samsung a54":        100_000,
    "samsung a53":         80_000,
    "pixel 8 pro":        260_000,
    "pixel 8":            190_000,
    "pixel 7 pro":        200_000,
    "pixel 7":            140_000,
    "xiaomi 13":          140_000,
    "xiaomi 12":          100_000,
    "poco x5 pro":         90_000,
    "poco x5":             70_000,
    "oneplus 11":         160_000,
    "motorola edge 40 pro": 140_000,
}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  SCRAPER LOGIKA                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

CONDITION_MAP = {1: "Új", 2: "Kiváló", 3: "Jó", 4: "Megfelelő", 6: "Gyűjthető"}

# ── Telefon azonosító kulcsszavak ─────────────────────────────────────────────
# Ha a cím NEM tartalmaz egyet sem ezek közül → kiszűrjük (cipő, ruha, stb.)
TELEFON_KULCSSZAVAK = [
    "iphone", "samsung", "galaxy", "pixel", "xiaomi", "poco", "redmi",
    "oneplus", "motorola", "huawei", "oppo", "realme", "nokia", "sony",
    "xperia", "honor", "vivo", "asus", "rog phone", "fairphone",
    "telefon", "mobiltelefon", "smartphone", "okostelefon",
    "128gb", "256gb", "64gb", "512gb", "16gb", "32gb",
]


def teljesiti_funkciokat(cim: str, leiras: str) -> tuple[bool, list[str]]:
    """
    Ellenőrzi hogy a termék teljesíti-e az aktív funkció szűrőket.
    Visszaadja: (megfelel-e, lista az aktív funkciókról)
    """
    szoveg = (cim + " " + leiras).lower()
    aktiv_funkciok = []

    for nev, beallitas in FUNKCIOK.items():
        if not beallitas["aktiv"]:
            continue

        # Tiltott szavak ellenőrzése
        if any(tiltott in szoveg for tiltott in beallitas["nem_tartalmaz"]):
            return False, []

        # Kulcsszó ellenőrzése (ha van)
        if beallitas["kulcsszavak"]:
            if not any(kw in szoveg for kw in beallitas["kulcsszavak"]):
                return False, []

        aktiv_funkciok.append(nev)

    return True, aktiv_funkciok


def azonosit_modellt(cim: str) -> str | None:
    """Megpróbálja azonosítani a telefon modelljét a cím alapján."""
    cim_lower = cim.lower()
    for modell in sorted(PIACI_ARAK.keys(), key=len, reverse=True):
        if modell in cim_lower:
            return modell
    return None


def arErtek_szazalek(ar: float, modell: str | None) -> float:
    """
    Visszaadja hány %-a az adott ár a piaci referencia árnak.
    60% = a piaci ár 60%-án kapható → nagyon jó
    100% = piaci áron = normális
    120%+ = drágább a piaci árnál → rossz ajánlat
    """
    if not modell:
        return 100.0   # ismeretlen modell → semleges
    piaci = PIACI_ARAK[modell]
    return round((ar / piaci) * 100, 1)


def pontszam(item: dict) -> float:
    """
    Ár-érték pontszám: minél kisebb, annál jobb.
    Figyelembe veszi: piaci ár %, állapot, eladói értékelés.
    """
    alap = item["arErtek_piaci_szazalek"]   # pl. 65.0

    # állapot szorzó: jobb állapot → kisebb pontszám
    allapot_szorzo = {1: 0.88, 2: 0.93, 3: 1.00, 4: 1.12}.get(
        int(item.get("allapot_id") or 3), 1.0
    )

    # értékelés bónusz: megbízható eladó → -5% max
    rating = item["ertekeles"]
    db     = item["ertekeles_db"]
    if db >= 10:
        rating_bonus = (rating / 5.0) * 0.05
    elif db >= 3:
        rating_bonus = (rating / 5.0) * 0.02
    else:
        rating_bonus = 0.0

    return round(alap * allapot_szorzo * (1 - rating_bonus), 2)


def parse_item(raw, query: str) -> dict | None:
    """Egy nyers Vinted item → tisztított dict, vagy None ha szűrve."""

    # ── Telefon szűrő — cipő/ruha/egyéb kiszűrése ────────────────────────────
    cim    = str(getattr(raw, "title", "") or "")
    leiras = str(getattr(raw, "description", "") or "")
    if not any(kw in cim.lower() for kw in TELEFON_KULCSSZAVAK):
        return None

    # ── Állapot ───────────────────────────────────────────────────────────────
    cond_id = getattr(raw, "status_id", None) or getattr(raw, "condition_id", None)
    try:
        cond_id_int = int(cond_id)
    except (TypeError, ValueError):
        cond_id_int = 3   # ismeretlen → "Jó"-nak vesszük
    if cond_id_int not in ACCEPTED_CONDITION_IDS:
        return None

    # ── Ár ────────────────────────────────────────────────────────────────────
    try:
        ar = float(str(getattr(raw, "price", 0)).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    if ar < MIN_PRICE or ar > MAX_PRICE:
        return None

    # ── Eladó ────────────────────────────────────────────────────────────────
    user = getattr(raw, "user", None)
    rating = float(getattr(user, "feedback_reputation", 0) or 0) if user else 0.0
    feedback_db = int(getattr(user, "positive_feedback_count", 0) or 0) if user else 0
    seller = getattr(user, "login", "ismeretlen") if user else "ismeretlen"
    if feedback_db >= MIN_SELLER_FEEDBACKS and rating < MIN_SELLER_RATING:
        return None


    # ── Funkció szűrők ───────────────────────────────────────────────────────
    megfelel, talalt_funkciok = teljesiti_funkciokat(cim, leiras)
    if not megfelel:
        return None

    # ── Modell azonosítás & piaci ár % ───────────────────────────────────────
    modell = azonosit_modellt(cim)
    piaci_szazalek = arErtek_szazalek(ar, modell)

    # ── Kép URL ──────────────────────────────────────────────────────────────
    photo = getattr(raw, "photo", None)
    if isinstance(photo, dict):
        kep_url = photo.get("url", "")
    else:
        kep_url = str(photo or "")

    return {
        "id":                    getattr(raw, "id", None),
        "cim":                   cim,
        "leiras_eleje":          leiras[:200],
        "ar_ft":                 ar,
        "allapot":               CONDITION_MAP.get(cond_id_int, "Ismeretlen"),
        "allapot_id":            cond_id_int,
        "elado":                 seller,
        "ertekeles":             round(rating, 2),
        "ertekeles_db":          feedback_db,
        "azonositott_modell":    modell,
        "piaci_referenciar":     PIACI_ARAK.get(modell) if modell else None,
        "arErtek_piaci_szazalek": piaci_szazalek,
        "funkciok":              talalt_funkciok,
        "url":                   getattr(raw, "url", ""),
        "kep_url":               kep_url,
        "kereses":               query,
        "scraped_at":            datetime.datetime.now().isoformat(),
    }


def scrape_query(scraper: VintedScraper, query: str) -> list[dict]:
    """Egy keresési kifejezéshez gyűjt találatokat."""
    print(f"  🔍 '{query}' ...", end="", flush=True)
    try:
        raw_items = scraper.search({
            "search_text":  query,
            "order":        "newest_first",
            "per_page":     96,
            "price_from":   MIN_PRICE,
            "price_to":     MAX_PRICE,
        })
    except Exception as e:
        print(f" ❌ HIBA: {e}")
        return []

    eredmenyek = []
    for raw in raw_items:
        parsed = parse_item(raw, query)
        if parsed:
            eredmenyek.append(parsed)

    print(f" {len(eredmenyek)} db (szűrve {len(raw_items)}-ből)")
    return eredmenyek


def deduplicate(items: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for item in items:
        iid = item.get("id")
        if iid and iid not in seen:
            seen.add(iid)
            unique.append(item)
    return unique


def generate_report(items: list[dict]) -> None:
    """Szöveges összefoglaló a top találatokról."""
    print(f"\n{'═'*72}")
    print("  TOP 15 LEGJOBB ÁR-ÉRTÉK ARÁNYÚ TELEFON")
    print(f"{'═'*72}")
    print(f"  {'#':<3} {'Cím':<36} {'Ár':>9}  {'Állapot':<10} {'Pont':>5}  {'Piaci%':>6}")
    print(f"  {'-'*68}")

    for i, item in enumerate(items[:15], 1):
        cim = item["cim"][:35]
        ar  = f"{item['ar_ft']:,.0f} Ft"
        all = item["allapot"]
        pont = item.get("arErtek_pontszam", "?")
        pct = f"{item['arErtek_piaci_szazalek']}%" if item["azonositott_modell"] else "n/a"
        modell_jel = f"  ← {item['azonositott_modell']}" if item["azonositott_modell"] else ""
        print(f"  {i:<3} {cim:<36} {ar:>9}  {all:<10} {pont:>5}  {pct:>6}{modell_jel}")
        if item["url"]:
            print(f"      {item['url']}")

    print()

    # Modell szerinti bontás
    modellek: dict[str, list] = {}
    for item in items:
        m = item.get("azonositott_modell")
        if m:
            modellek.setdefault(m, []).append(item["ar_ft"])

    if modellek:
        print(f"\n  MODELL ÖSSZESÍTŐ (legolcsóbb ajánlat / átlag)")
        print(f"  {'-'*50}")
        for modell, arak in sorted(modellek.items(), key=lambda x: min(x[1])):
            min_ar  = min(arak)
            atlag   = sum(arak) / len(arak)
            piaci   = PIACI_ARAK.get(modell, 0)
            megtakaritas = (1 - min_ar / piaci) * 100 if piaci else 0
            print(
                f"  {modell:<30}  min: {min_ar:>9,.0f} Ft"
                f"  átlag: {atlag:>9,.0f} Ft"
                + (f"  ({megtakaritas:+.0f}% a piaci árhoz képest)" if piaci else "")
            )
    print()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  BELÉPÉSI PONT                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main():
    print("=" * 72)
    print("  Vinted Telefon Ár-Érték Scraper")
    print(f"  {BASE_URL}  |  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    aktiv_szurok = [n for n, b in FUNKCIOK.items() if b["aktiv"]]
    if aktiv_szurok:
        print(f"  Aktív funkció szűrők: {', '.join(aktiv_szurok)}")
    print("=" * 72)

    scraper   = VintedScraper(BASE_URL)
    osszes: list[dict] = []

    for query in SEARCH_QUERIES:
        eredmenyek = scrape_query(scraper, query)
        osszes.extend(eredmenyek)
        time.sleep(1.5)   # udvarias szünet a kérések közt

    print(f"\n  Összegyűjtve: {len(osszes)} db")
    egyedi = deduplicate(osszes)
    print(f"  Duplikátum szűrés után: {len(egyedi)} db")

    # Pontszám kiszámítása és rendezés
    for item in egyedi:
        item["arErtek_pontszam"] = pontszam(item)
    rendezett = sorted(egyedi, key=lambda x: x["arErtek_pontszam"])

    # Mentés
    DATA_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rendezett, f, ensure_ascii=False, indent=2)
    print(f"  Mentve: {OUTPUT_FILE}")

    generate_report(rendezett)
    print("  ✅ Kész! Következő lépés: tekintsd meg a data/results.json fájlt.")
    print("     Vagy futtasd: python analyzer.py  (AI elemzés Claude API-val)")


if __name__ == "__main__":
    main()
