"""Inlezen van Hundegger-productiebestanden (BVX / XML-varianten).

Hygiene:
- XML wordt gelezen met defusedxml (bescherming tegen XXE en 'billion laughs').
- Bestandsgrootte wordt begrensd.
- Elk onderdeel met ontbrekende of onlogische waarden levert een waarschuwing op
  in plaats van stil een 0 of een crash.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .bewerkingen import classificeer

MAX_BESTANDSGROOTTE = 20 * 1024 * 1024  # 20 MB

XML_EXTENSIES = {"bvx", "xml", "hmlx"}
NOG_NIET_ONDERSTEUND = {"hmm"}
ALLE_EXTENSIES = sorted(XML_EXTENSIES | NOG_NIET_ONDERSTEUND)


class BestandFout(Exception):
    """Fout die als nette melding aan de gebruiker getoond kan worden."""


@dataclass
class Onderdeel:
    positie: str
    aantal: int
    dikte: float
    breedte: float
    lengte: float
    kwaliteit: str
    tekst: str  # naam + kwaliteit + opmerkingen, gebruikt voor schaafcodes
    bewerkingen: dict[str, int] = field(default_factory=dict)


@dataclass
class ParseResultaat:
    projectnaam: str
    onderdelen: list[Onderdeel]
    waarschuwingen: list[str]
    sha256: str


def _getal(waarde: str | None, standaard: float | None = None) -> float | None:
    if waarde is None or str(waarde).strip() == "":
        return standaard
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def _projectnaam(root: Element, tekst: str) -> str:
    # Let op: 'if element' is onbetrouwbaar (een element zonder kinderen is falsy).
    # Dat was de oorzaak van 'Project onbekend' in v1. Daarom altijd 'is not None'.
    kandidaten: list[str | None] = []
    job = root.find(".//Job")
    if job is not None:
        kandidaten += [job.get("Project"), job.get("ProjectName"), job.get("Name")]
    kandidaten += [root.get("Project"), root.get("ProjectName")]
    if root.tag == "Project":
        kandidaten.append(root.get("Name"))
    for k in kandidaten:
        if k and k.strip():
            return k.strip()
    match = re.search(r"<!--\s*project\s*:?\s*([^>]+?)\s*-->", tekst, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def lees_bestand(bestandsnaam: str, data: bytes) -> ParseResultaat:
    extensie = bestandsnaam.rsplit(".", 1)[-1].lower() if "." in bestandsnaam else ""
    if extensie in NOG_NIET_ONDERSTEUND:
        raise BestandFout(
            f".{extensie}-bestanden worden nog niet ondersteund. "
            "Stuur een voorbeeldbestand mee, dan kan de inleesfunctie worden toegevoegd."
        )
    if extensie not in XML_EXTENSIES:
        raise BestandFout(f"Bestandstype .{extensie or '?'} wordt niet ondersteund.")
    if len(data) == 0:
        raise BestandFout("Het bestand is leeg.")
    if len(data) > MAX_BESTANDSGROOTTE:
        raise BestandFout(f"Bestand is groter dan {MAX_BESTANDSGROOTTE // (1024 * 1024)} MB.")

    tekst = data.decode("utf-8-sig", errors="replace")
    try:
        root = SafeET.fromstring(tekst)
    except DefusedXmlException:
        raise BestandFout("Het bestand bevat onveilige XML-constructies en is geweigerd.")
    except SafeET.ParseError as e:
        raise BestandFout(f"Het bestand is geen geldige XML ({e}).")

    onderdelen: list[Onderdeel] = []
    waarschuwingen: list[str] = []

    for i, part in enumerate(root.iter("Part"), start=1):
        positie = (part.get("Name") or "").strip() or f"(regel {i})"

        aantal_f = _getal(part.get("ReqQuantity"), 1)
        if aantal_f is None or aantal_f <= 0 or aantal_f != int(aantal_f):
            waarschuwingen.append(f"{positie}: ongeldig aantal '{part.get('ReqQuantity')}', onderdeel overgeslagen.")
            continue

        maten = {}
        for attr in ("Width", "Height", "Length"):
            w = _getal(part.get(attr))
            if w is None or w <= 0:
                waarschuwingen.append(f"{positie}: ontbrekende of ongeldige {attr} '{part.get(attr)}'.")
                w = 0.0
            maten[attr] = w

        bewerkingen: dict[str, int] = {}
        ops = part.find("Operations")
        if ops is not None:
            for op in ops:
                code = classificeer(op.tag, op.attrib)
                if code:
                    bewerkingen[code] = bewerkingen.get(code, 0) + 1

        kwaliteit = (part.get("Grade") or "").strip()
        onderdelen.append(
            Onderdeel(
                positie=positie,
                aantal=int(aantal_f),
                dikte=maten["Width"],
                breedte=maten["Height"],
                lengte=maten["Length"],
                kwaliteit=kwaliteit,
                tekst=" ".join(filter(None, [part.get("Name"), kwaliteit, part.get("Comments")])),
                bewerkingen=bewerkingen,
            )
        )

    if not onderdelen:
        raise BestandFout("Geen onderdelen (<Part>) gevonden in dit bestand. Is dit wel een Hundegger-productiebestand?")

    return ParseResultaat(
        projectnaam=_projectnaam(root, tekst),
        onderdelen=onderdelen,
        waarschuwingen=waarschuwingen,
        sha256=hashlib.sha256(data).hexdigest(),
    )
