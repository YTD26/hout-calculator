"""Gebruiksteller: registreert elke verwerkte upload, zonder klantgegevens.

Per upload wordt alleen opgeslagen:
    tijdstip (UTC), app-versie, bestandstype, grootte in kB,
    aantal regels en delen, en de SHA-256 van het bestand
    (om herhaalde uploads van hetzelfde bestand te herkennen).
Geen bestandsnaam, projectnaam, klantnaam of inhoud.

Opslag:
- Is er een database ingesteld (secrets TELLER_SUPABASE_URL en TELLER_SUPABASE_KEY),
  dan gaat elke registratie naar de tabel `uploads` in die database.
- Anders naar een lokaal bestand (data/uploads.jsonl). Let op: op Streamlit
  Community Cloud verdwijnt dat bestand bij een herstart van de app.

Fouten in de teller mogen de calculatie nooit blokkeren: alles wordt afgevangen en gelogd.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("houtcalc.teller")

LOKAAL_PAD = Path(__file__).resolve().parent.parent / "data" / "uploads.jsonl"


@dataclass
class Registratie:
    tijdstip: str
    app_versie: str
    bestandstype: str
    grootte_kb: int
    regels: int
    delen: int
    sha256: str


def maak_registratie(bestandsnaam: str, grootte_bytes: int, regels: int, delen: int,
                     sha256: str, app_versie: str) -> Registratie:
    ext = bestandsnaam.rsplit(".", 1)[-1].lower() if "." in bestandsnaam else ""
    return Registratie(
        tijdstip=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        app_versie=app_versie,
        bestandstype=ext,
        grootte_kb=round(grootte_bytes / 1024),
        regels=regels,
        delen=delen,
        sha256=sha256,
    )


def _naar_supabase(reg: Registratie, url: str, sleutel: str, timeout: float = 5.0) -> None:
    verzoek = urllib.request.Request(
        url.rstrip("/") + "/rest/v1/uploads",
        data=json.dumps(asdict(reg)).encode("utf-8"),
        method="POST",
        headers={"apikey": sleutel, "Authorization": f"Bearer {sleutel}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"},
    )
    with urllib.request.urlopen(verzoek, timeout=timeout) as antwoord:
        if antwoord.status >= 300:
            raise RuntimeError(f"HTTP {antwoord.status}")


def _naar_bestand(reg: Registratie, pad: Path) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with open(pad, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(reg)) + "\n")


def registreer(reg: Registratie, supabase_url: str | None = None, supabase_key: str | None = None,
               pad: Path = LOKAAL_PAD) -> str:
    """Slaat de registratie op. Geeft terug waar ('database', 'bestand' of 'mislukt')."""
    if supabase_url and supabase_key:
        try:
            _naar_supabase(reg, supabase_url, supabase_key)
            return "database"
        except Exception as e:  # netwerk/DB-fout: terugvallen op bestand
            log.warning("Teller: database niet bereikbaar (%s), schrijf naar bestand", e)
    try:
        _naar_bestand(reg, pad)
        return "bestand"
    except Exception as e:
        log.warning("Teller: registratie mislukt (%s)", e)
        return "mislukt"


def lees_lokaal(pad: Path = LOKAAL_PAD) -> list[dict]:
    if not pad.exists():
        return []
    regels = []
    for regel in pad.read_text(encoding="utf-8").splitlines():
        try:
            regels.append(json.loads(regel))
        except json.JSONDecodeError:
            continue
    return regels
