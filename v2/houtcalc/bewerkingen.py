"""Bewerkingscodes uit Hundegger-bestanden en hun Nederlandse weergavenamen.

De Nederlandse namen staan in config/bewerkingen.json zodat Heuvelman ze kan
aanpassen zonder codewijziging. Codes die daar niet in staan worden NIET
weggegooid: ze verschijnen met hun originele code en een waarschuwing.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PAD = Path(__file__).resolve().parent.parent / "config" / "bewerkingen.json"

# Elementen in <Operations> die geen bewerking zijn en dus niet geteld worden.
# BvnMacro is in v2 bewust NIET genegeerd: in echte bestanden (bv. P250014) staan
# honderden macro's (Id 0402) die v1 stil wegliet. Ze worden geteld als BvnMacro_<Id>.
GENEGEERDE_ELEMENTEN = {"TextOutput"}

# Zaagsnede binnen deze afwijking (graden) van 90 telt als recht.
HOEK_TOLERANTIE = 0.1


def laad_namen(pad: Path = CONFIG_PAD) -> dict[str, str]:
    with open(pad, encoding="utf-8") as f:
        data = json.load(f)
    return {code: info["naam"] for code, info in data["bewerkingen"].items()}


def classificeer(tag: str, attrib: dict[str, str]) -> str | None:
    """Zet een XML-element om naar een bewerkingscode, of None als het genegeerd wordt."""
    if tag in GENEGEERDE_ELEMENTEN:
        return None
    if tag == "BvnMacro":
        return f"BvnMacro_{(attrib.get('Id') or 'onbekend').strip()}"
    if tag == "SawCut":
        try:
            hoek = float(attrib.get("Angle", 90))
            bevel = float(attrib.get("Bevel", 90))
        except ValueError:
            return "SawCut_Schuin"  # onleesbare hoek: liever het duurdere tarief dan stil te laag
        recht = abs(hoek - 90.0) < HOEK_TOLERANTIE and abs(bevel - 90.0) < HOEK_TOLERANTIE
        return "SawCut_Recht" if recht else "SawCut_Schuin"
    return tag


def weergavenaam(code: str, namen: dict[str, str]) -> str:
    return namen.get(code, code)
