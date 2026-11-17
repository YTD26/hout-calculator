"""Vergelijking met v1: wat de oude tool voor hetzelfde bestand zou rekenen.

Herbouwt de rekenregels van v1 (app.py in de root van de repo), met de prijzen
uit het actieve profiel, zodat het verschil puur door de rekenregels komt:
- bewerkingen altijd per stuk; BvnMacro telt niet mee (v1 negeerde die);
- toeslag schaven per m1 als er een schaafcode is OF de maat niet binnen 1 mm
  van de vaste lijst ruwe maten valt;
- stelkosten korten altijd, stelkosten schaven als er ergens een toeslag is.
"""

from __future__ import annotations

import pandas as pd

from .parser import Onderdeel
from .prijzen import Calculatie, Prijsprofiel

# Letterlijk uit v1
V1_RUWE_MATEN = [(38.0, 89.0), (38.0, 120.0), (38.0, 140.0), (38.0, 170.0),
                 (38.0, 235.0), (45.0, 70.0), (50.0, 100.0), (75.0, 200.0)]
V1_SCHAAFCODES = ["G10-1", "G10-5", "GESCHAAFD"]


def _v1_toeslag(o: Onderdeel) -> bool:
    tekst = o.tekst.upper()
    if any(c in tekst for c in V1_SCHAAFCODES):
        return True
    for d, b in V1_RUWE_MATEN:
        if (abs(o.dikte - d) < 1.0 and abs(o.breedte - b) < 1.0) or \
           (abs(o.dikte - b) < 1.0 and abs(o.breedte - d) < 1.0):
            return False
    return True


def vergelijk(onderdelen: list[Onderdeel], profiel: Prijsprofiel, calc_v2: Calculatie) -> dict:
    bew_v1 = 0.0
    toeslag_v1 = 0.0
    meters_v1 = 0.0
    regels_v1 = 0
    for o in onderdelen:
        for code, n in o.bewerkingen.items():
            if code.startswith("BvnMacro"):
                continue
            bp = profiel.bewerkingen.get(code)
            if bp is not None:
                bew_v1 += bp.prijs * n * o.aantal
        if _v1_toeslag(o):
            m = o.lengte / 1000.0 * o.aantal
            meters_v1 += m
            toeslag_v1 += m * profiel.toeslag_schaven_m1
            regels_v1 += 1

    stel_schaven_v1 = profiel.stelkosten_schaven if regels_v1 else 0.0
    stel_korten_v1 = profiel.stelkosten_korten

    po = calc_v2.prijsopbouw
    is_toeslag = po["Post"].str.startswith("Toeslag")
    bew_v2 = float(po.loc[~is_toeslag & (po["Methode"] != "Per order"), "Bedrag"].sum())
    toeslag_v2 = float(po.loc[is_toeslag, "Bedrag"].sum())
    stel_schaven_v2 = float(po.loc[po["Post"] == "Stelkosten schaven", "Bedrag"].sum())
    stel_korten_v2 = float(po.loc[po["Post"] == "Stelkosten korten", "Bedrag"].sum())

    rijen = [
        ("Bewerkingen", bew_v1, bew_v2),
        ("Toeslag schaven / afwijkende maat", toeslag_v1, toeslag_v2),
        ("Stelkosten schaven", stel_schaven_v1, stel_schaven_v2),
        ("Stelkosten korten", stel_korten_v1, stel_korten_v2),
    ]
    tabel = pd.DataFrame([{"Post": p, "v1": round(a, 2), "v2": round(b, 2), "Verschil": round(b - a, 2)}
                          for p, a, b in rijen])
    totaal_v1 = round(float(tabel["v1"].sum()), 2)
    tabel.loc[len(tabel)] = {"Post": "Totaal excl. BTW", "v1": totaal_v1, "v2": calc_v2.totaal,
                             "Verschil": round(calc_v2.totaal - totaal_v1, 2)}
    return {
        "tabel": tabel,
        "totaal_v1": totaal_v1,
        "verschil": round(calc_v2.totaal - totaal_v1, 2),
        "regels_toeslag_v1": regels_v1,
        "meters_toeslag_v1": round(meters_v1, 1),
        "regels_totaal": len(onderdelen),
    }
