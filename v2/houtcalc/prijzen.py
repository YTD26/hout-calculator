"""Prijsprofielen en de calculatie.

Een prijsprofiel hoort bij een klant (of is het standaardprofiel). Per bewerking
staat een prijs en een methode:
- "per_stuk": prijs x aantal keer dat de bewerking voorkomt x aantal delen
- "per_deel": prijs x aantal delen waarop de bewerking minstens 1x voorkomt

Toeslagen per strekkende meter:
- afwijkende kopmaat (buiten de kopmatenlijst +/- tolerantie)
- schaven volgens code (G10-1, G10-5, GESCHAAFD) bij een standaard kopmaat
  Is de maat afwijkend, dan geldt alleen de afwijkende-maat toeslag (geen dubbele toeslag).

Stelkosten per order:
- schaven: als minstens 1 deel een schaaf- of afwijkende-maat toeslag krijgt
- korten: volgens regel 'altijd' | 'bij_zaagsneden' | 'nooit'
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import kopmaten as km
from .bewerkingen import weergavenaam
from .parser import Onderdeel

PROFIELEN_MAP = Path(__file__).resolve().parent.parent / "config" / "profielen"

METHODES = {"per_stuk": "Per stuk", "per_deel": "Per deel"}
KORTEN_REGELS = {"bij_zaagsneden": "Alleen bij zaagsneden", "altijd": "Altijd", "nooit": "Nooit"}
SCHAAF_CODES = ["G10-1", "G10-5", "GESCHAAFD"]


class ProfielFout(Exception):
    pass


@dataclass
class BewerkingPrijs:
    prijs: float
    methode: str = "per_stuk"


@dataclass
class Prijsprofiel:
    naam: str
    bewerkingen: dict[str, BewerkingPrijs]
    toeslag_schaven_m1: float = 0.0
    toeslag_afwijkende_maat_m1: float = 0.0
    stelkosten_schaven: float = 0.0
    stelkosten_korten: float = 0.0
    korten_regel: str = "bij_zaagsneden"
    schaafcodes: list[str] = field(default_factory=lambda: list(SCHAAF_CODES))

    # ---------- (de)serialisatie met validatie ----------
    @classmethod
    def van_dict(cls, d: dict) -> "Prijsprofiel":
        try:
            bew = {}
            for code, v in d["bewerkingen"].items():
                prijs = float(v["prijs"])
                methode = v.get("methode", "per_stuk")
                if prijs < 0:
                    raise ProfielFout(f"Negatieve prijs voor {code}.")
                if methode not in METHODES:
                    raise ProfielFout(f"Onbekende methode '{methode}' voor {code}.")
                bew[code] = BewerkingPrijs(prijs, methode)
            t, s = d.get("toeslagen", {}), d.get("stelkosten", {})
            profiel = cls(
                naam=str(d["naam"]).strip() or "Naamloos",
                bewerkingen=bew,
                toeslag_schaven_m1=float(t.get("schaven_m1", 0)),
                toeslag_afwijkende_maat_m1=float(t.get("afwijkende_maat_m1", 0)),
                stelkosten_schaven=float(s.get("schaven", 0)),
                stelkosten_korten=float(s.get("korten", 0)),
                korten_regel=s.get("korten_regel", "bij_zaagsneden"),
                schaafcodes=[c.strip().upper() for c in d.get("schaafcodes", SCHAAF_CODES) if c.strip()],
            )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise ProfielFout(f"Prijsprofiel is onvolledig of ongeldig: {e}") from e
        if profiel.korten_regel not in KORTEN_REGELS:
            raise ProfielFout(f"Onbekende korten-regel '{profiel.korten_regel}'.")
        for v in (profiel.toeslag_schaven_m1, profiel.toeslag_afwijkende_maat_m1,
                  profiel.stelkosten_schaven, profiel.stelkosten_korten):
            if v < 0:
                raise ProfielFout("Toeslagen en stelkosten mogen niet negatief zijn.")
        return profiel

    def naar_dict(self) -> dict:
        return {
            "naam": self.naam,
            "bewerkingen": {c: {"prijs": b.prijs, "methode": b.methode} for c, b in self.bewerkingen.items()},
            "toeslagen": {"schaven_m1": self.toeslag_schaven_m1,
                          "afwijkende_maat_m1": self.toeslag_afwijkende_maat_m1},
            "stelkosten": {"schaven": self.stelkosten_schaven, "korten": self.stelkosten_korten,
                           "korten_regel": self.korten_regel},
            "schaafcodes": self.schaafcodes,
        }

    def naar_json(self) -> str:
        return json.dumps(self.naar_dict(), indent=2, ensure_ascii=False)


def laad_profielen(map_: Path = PROFIELEN_MAP) -> dict[str, Prijsprofiel]:
    profielen = {}
    for pad in sorted(map_.glob("*.json")):
        with open(pad, encoding="utf-8") as f:
            p = Prijsprofiel.van_dict(json.load(f))
        profielen[p.naam] = p
    return profielen


# ---------- calculatie ----------

@dataclass
class Calculatie:
    regels: pd.DataFrame           # 1 rij per onderdeel
    bewerkingscodes: list[str]     # volgorde van de bewerkingskolommen (codes)
    prijsopbouw: pd.DataFrame      # 1 rij per bewerking / toeslag / stelpost
    stelkosten: float
    totaal: float
    zonder_prijs: list[str]        # bewerkingscodes in het bestand zonder prijs in het profiel


def bereken(onderdelen: list[Onderdeel], profiel: Prijsprofiel, namen: dict[str, str],
            kopmatenlijst: list[km.Kopmaat], tolerantie: float = km.STANDAARD_TOLERANTIE_MM) -> Calculatie:
    # Kolomvolgorde: eerst bekende codes uit het profiel, daarna onbekende in volgorde van voorkomen.
    gevonden: list[str] = []
    for o in onderdelen:
        for c in o.bewerkingen:
            if c not in gevonden:
                gevonden.append(c)
    codes = [c for c in profiel.bewerkingen if c in gevonden] + [c for c in gevonden if c not in profiel.bewerkingen]
    zonder_prijs = [c for c in gevonden if c not in profiel.bewerkingen]

    rijen = []
    for o in onderdelen:
        meters = o.lengte / 1000.0 * o.aantal
        kop = km.beoordeel(o.dikte, o.breedte, kopmatenlijst, tolerantie)
        tekst = o.tekst.upper()
        schaafcode = next((c for c in profiel.schaafcodes if c in tekst), "")

        if kop == km.AFWIJKEND:
            toeslag_soort, toeslag = "Afwijkende maat", meters * profiel.toeslag_afwijkende_maat_m1
        elif schaafcode:
            toeslag_soort, toeslag = f"Schaven ({schaafcode})", meters * profiel.toeslag_schaven_m1
        else:
            toeslag_soort, toeslag = "", 0.0

        bew_prijs = 0.0
        for code, n in o.bewerkingen.items():
            bp = profiel.bewerkingen.get(code)
            if bp is None:
                continue
            bew_prijs += bp.prijs * (o.aantal if bp.methode == "per_deel" else n * o.aantal)

        per_deel = sum(o.bewerkingen.values())
        rij = {
            "Positie": o.positie, "Aantal": o.aantal, "Dikte": o.dikte, "Breedte": o.breedte,
            "Lengte (mm)": round(o.lengte), "Kwaliteit": o.kwaliteit,
        }
        for c in codes:
            rij[c] = o.bewerkingen.get(c, 0)
        rij.update({
            "Bewerkingen per deel": per_deel,
            "Bewerkingen totaal": per_deel * o.aantal,
            "Kopmaat": kop,
            "Schaafcode": schaafcode,
            "Toeslag": toeslag_soort,
            "Meters": round(meters, 3),
            "Bedrag bewerkingen": round(bew_prijs, 2),
            "Bedrag toeslag": round(toeslag, 2),
            "Regeltotaal": round(bew_prijs + toeslag, 2),
        })
        rijen.append(rij)
    regels = pd.DataFrame(rijen)

    # Prijsopbouw
    opbouw = []
    for c in codes:
        bp = profiel.bewerkingen.get(c)
        kol = regels[c]
        stuks = int((kol * regels["Aantal"]).sum())
        delen = int(regels.loc[kol > 0, "Aantal"].sum())
        if bp is None:
            opbouw.append({"Post": weergavenaam(c, namen), "Code": c, "Methode": "GEEN PRIJS",
                           "Hoeveelheid": stuks, "Prijs": 0.0, "Bedrag": 0.0})
            continue
        hoeveel = delen if bp.methode == "per_deel" else stuks
        opbouw.append({"Post": weergavenaam(c, namen), "Code": c, "Methode": METHODES[bp.methode],
                       "Hoeveelheid": hoeveel, "Prijs": bp.prijs, "Bedrag": round(hoeveel * bp.prijs, 2)})

    for soort, tarief, masker in (
        ("Toeslag afwijkende maat (m1)", profiel.toeslag_afwijkende_maat_m1, regels["Toeslag"] == "Afwijkende maat"),
        ("Toeslag schaven (m1)", profiel.toeslag_schaven_m1, regels["Toeslag"].str.startswith("Schaven")),
    ):
        m = float(regels.loc[masker, "Meters"].sum())
        if m > 0:
            opbouw.append({"Post": soort, "Code": "", "Methode": "Per m1", "Hoeveelheid": round(m, 3),
                           "Prijs": tarief, "Bedrag": round(float(regels.loc[masker, "Bedrag toeslag"].sum()), 2)})

    heeft_toeslag = bool((regels["Toeslag"] != "").any())
    heeft_zaagsneden = any(("SawCut_Recht" in o.bewerkingen or "SawCut_Schuin" in o.bewerkingen) for o in onderdelen)
    korten = {"altijd": True, "nooit": False, "bij_zaagsneden": heeft_zaagsneden}[profiel.korten_regel]

    stelkosten = 0.0
    if heeft_toeslag and profiel.stelkosten_schaven:
        stelkosten += profiel.stelkosten_schaven
        opbouw.append({"Post": "Stelkosten schaven", "Code": "", "Methode": "Per order", "Hoeveelheid": 1,
                       "Prijs": profiel.stelkosten_schaven, "Bedrag": profiel.stelkosten_schaven})
    if korten and profiel.stelkosten_korten:
        stelkosten += profiel.stelkosten_korten
        opbouw.append({"Post": "Stelkosten korten", "Code": "", "Methode": "Per order", "Hoeveelheid": 1,
                       "Prijs": profiel.stelkosten_korten, "Bedrag": profiel.stelkosten_korten})

    prijsopbouw = pd.DataFrame(opbouw, columns=["Post", "Code", "Methode", "Hoeveelheid", "Prijs", "Bedrag"])
    totaal = round(float(regels["Regeltotaal"].sum()) + stelkosten, 2)
    return Calculatie(regels, codes, prijsopbouw, round(stelkosten, 2), totaal, zonder_prijs)
