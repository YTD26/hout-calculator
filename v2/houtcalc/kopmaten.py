"""Controle van de kopmaat (dikte x breedte) tegen de standaard netto kopmatenlijst.

Regel (verzoek Heuvelman, 17-11-2026): een maat is standaard als hij binnen
de tolerantie (standaard 2 mm, inclusief) van een standaard netto kopmaat valt.
Voorbeeld: standaard 30x170 -> 30x172 en 30x168 zijn ook standaard.
Liggend of staand maakt niet uit (170x30 = 30x170).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

CONFIG_PAD = Path(__file__).resolve().parent.parent / "config" / "kopmaten.csv"
STANDAARD_TOLERANTIE_MM = 2.0

STANDAARD = "Standaard"
AFWIJKEND = "Afwijkend"
ONBEKEND = "Onbekend"  # geen kopmatenlijst ingesteld: niet te beoordelen

Kopmaat = tuple[float, float]


def lees_csv(inhoud: str) -> list[Kopmaat]:
    """Leest 'dikte;breedte' of 'dikte,breedte' per regel. Kopregel en lege regels mogen."""
    maten: list[Kopmaat] = []
    scheiding = ";" if ";" in inhoud else ","
    for rij in csv.reader(io.StringIO(inhoud), delimiter=scheiding):
        if len(rij) < 2:
            continue
        try:
            d, b = float(rij[0].strip().replace(",", ".")), float(rij[1].strip().replace(",", "."))
        except ValueError:
            continue  # kopregel of commentaar
        if d > 0 and b > 0:
            maten.append((d, b))
    return sorted(set(maten))


def laad_standaard(pad: Path = CONFIG_PAD) -> list[Kopmaat]:
    return lees_csv(pad.read_text(encoding="utf-8"))


def naar_csv(maten: list[Kopmaat]) -> str:
    regels = ["dikte;breedte"] + [f"{d:g};{b:g}" for d, b in maten]
    return "\n".join(regels) + "\n"


def beoordeel(dikte: float, breedte: float, maten: list[Kopmaat],
              tolerantie: float = STANDAARD_TOLERANTIE_MM) -> str:
    if not maten:
        return ONBEKEND
    eps = 1e-9  # afrondingsruis: 2.0000001 mm telt nog als 2 mm
    for sd, sb in maten:
        for d, b in ((dikte, breedte), (breedte, dikte)):
            if abs(d - sd) <= tolerantie + eps and abs(b - sb) <= tolerantie + eps:
                return STANDAARD
    return AFWIJKEND
