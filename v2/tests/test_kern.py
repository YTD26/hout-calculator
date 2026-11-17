from pathlib import Path

import pytest
from openpyxl import load_workbook
from io import BytesIO

from houtcalc import kopmaten as km
from houtcalc.bewerkingen import classificeer, laad_namen
from houtcalc.export import maak_excel
from houtcalc.parser import BestandFout, lees_bestand
from houtcalc.prijzen import Prijsprofiel, ProfielFout, bereken, laad_profielen

DATA = Path(__file__).parent / "data" / "voorbeeld.bvx"


@pytest.fixture
def resultaat():
    return lees_bestand("voorbeeld.bvx", DATA.read_bytes())


@pytest.fixture
def profiel():
    return laad_profielen()["Standaard"]


# ---------- parser ----------

def test_projectnaam_uit_job_zonder_kinderen(resultaat):
    # v1-bug: <Job Project="..."/> zonder kindelementen gaf 'Onbekend'
    assert resultaat.projectnaam == "Testproject Schorrenweg"


def test_projectnaam_uit_commentaar():
    xml = b'<!-- project: Veranda Blok 30 --><R><Part Name="A" Width="1" Height="1" Length="1"/></R>'
    assert lees_bestand("x.bvx", xml).projectnaam == "Veranda Blok 30"


def test_bewerkingen_geteld_en_textoutput_genegeerd(resultaat):
    p1 = resultaat.onderdelen[0]
    assert p1.bewerkingen == {"SawCut_Recht": 1, "SawCut_Schuin": 1, "Lap": 1, "Drill": 1}


def test_onbekende_bewerking_blijft_behouden(resultaat):
    assert resultaat.onderdelen[1].bewerkingen["Pocket"] == 1


def test_bom_wordt_geaccepteerd():
    xml = "﻿<R><Part Name='A' Width='30' Height='170' Length='100'/></R>".encode("utf-8")
    assert lees_bestand("a.xml", xml).onderdelen[0].positie == "A"


@pytest.mark.parametrize("naam,data,tekst", [
    ("a.hmm", b"x", "nog niet ondersteund"),
    ("a.pdf", b"x", "niet ondersteund"),
    ("a.bvx", b"", "leeg"),
    ("a.bvx", b"<niet-af", "geen geldige XML"),
    ("a.bvx", b"<R><X/></R>", "Geen onderdelen"),
])
def test_nette_foutmeldingen(naam, data, tekst):
    with pytest.raises(BestandFout, match=tekst):
        lees_bestand(naam, data)


def test_xxe_wordt_geweigerd():
    xml = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
    with pytest.raises(BestandFout):
        lees_bestand("a.bvx", xml)


def test_ongeldig_aantal_geeft_waarschuwing():
    xml = b"<R><Part Name='A' ReqQuantity='-2' Width='30' Height='170' Length='100'/>" \
          b"<Part Name='B' Width='30' Height='170' Length='100'/></R>"
    r = lees_bestand("a.bvx", xml)
    assert [o.positie for o in r.onderdelen] == ["B"]
    assert any("ongeldig aantal" in w for w in r.waarschuwingen)


def test_hoekclassificatie():
    assert classificeer("SawCut", {"Angle": "90", "Bevel": "90"}) == "SawCut_Recht"
    assert classificeer("SawCut", {"Angle": "60"}) == "SawCut_Schuin"
    assert classificeer("SawCut", {"Angle": "abc"}) == "SawCut_Schuin"
    assert classificeer("TextOutput", {}) is None
    # v1 liet macro's stil weg; v2 telt ze zodat ze zichtbaar zijn en geprijsd kunnen worden
    assert classificeer("BvnMacro", {"Id": "0402"}) == "BvnMacro_0402"


def test_element_en_macro_uit_bestand():
    xml = (b"<!-- project: P1 --><Job><Parts><Part Name='H7' Unit='BU-001' ReqQuantity='2' Width='38' "
           b"Height='235' Length='2591'><Operations><SawCut/><BvnMacro Id='0402'/><BvnMacro Id='0402'/>"
           b"<TextOutput/></Operations></Part></Parts></Job>")
    r = lees_bestand("a.bvx", xml)
    o = r.onderdelen[0]
    assert r.projectnaam == "P1" and o.element == "BU-001"
    assert o.bewerkingen == {"SawCut_Recht": 1, "BvnMacro_0402": 2}


# ---------- kopmaten ----------

@pytest.mark.parametrize("d,b,verwacht", [
    (30, 170, km.STANDAARD), (30, 172, km.STANDAARD), (30, 168, km.STANDAARD),
    (170, 30, km.STANDAARD), (30, 172.5, km.AFWIJKEND), (30, 167.9, km.AFWIJKEND), (38, 140, km.AFWIJKEND),
])
def test_kopmaat_tolerantie(d, b, verwacht):
    assert km.beoordeel(d, b, [(30, 170)]) == verwacht


def test_kopmaat_zonder_lijst_is_onbekend():
    assert km.beoordeel(30, 170, []) == km.ONBEKEND


def test_kopmaten_csv_roundtrip():
    maten = km.lees_csv("dikte;breedte\n30;170\n45,5;95\nonzin\n")
    assert maten == [(30.0, 170.0), (45.5, 95.0)]  # komma als decimaal in een ;-bestand
    assert km.lees_csv(km.naar_csv([(30, 170), (44, 120)])) == [(30, 170), (44, 120)]


# ---------- prijzen ----------

def test_calculatie_per_stuk(resultaat, profiel):
    calc = bereken(resultaat.onderdelen, profiel, laad_namen(), [(30, 170)])
    r = calc.regels.set_index("Positie")
    # P1: 4 st x (0.50 + 0.90 + 3.75 + 0.95) = 24.40, standaardmaat, geen toeslag
    assert r.loc["P1", "Bedrag bewerkingen"] == pytest.approx(24.40)
    assert r.loc["P1", "Bedrag toeslag"] == 0
    # P2: 2 st x 2 x 0.50 = 2.00; 30x172 is standaard, G10-1 -> schaaftoeslag 4.8 m x 1.25 = 6.00
    assert r.loc["P2", "Kopmaat"] == km.STANDAARD
    assert r.loc["P2", "Toeslag"] == "Schaven (G10-1)"
    assert r.loc["P2", "Bedrag toeslag"] == pytest.approx(6.00)
    # P3: 38x140 afwijkend -> 10 m x 1.25 = 12.50
    assert r.loc["P3", "Toeslag"] == "Afwijkende maat"
    assert r.loc["P3", "Bedrag toeslag"] == pytest.approx(12.50)
    # stelkosten: schaven 50 + korten 25 (er zijn zaagsneden)
    assert calc.stelkosten == pytest.approx(75.0)
    assert calc.totaal == pytest.approx(24.40 + 2.00 + 6.00 + 12.50 + 75.0)
    assert calc.zonder_prijs == ["Pocket"]


def test_prijsopbouw_sluit_aan_op_totaal(resultaat, profiel):
    calc = bereken(resultaat.onderdelen, profiel, laad_namen(), [(30, 170)])
    assert calc.prijsopbouw["Bedrag"].sum() == pytest.approx(calc.totaal)


def test_per_deel_prijzing(resultaat, profiel):
    profiel.bewerkingen["SawCut_Recht"].methode = "per_deel"
    calc = bereken(resultaat.onderdelen, profiel, laad_namen(), [(30, 170)])
    r = calc.regels.set_index("Positie")
    # P2 heeft 2 rechte zaagsneden per deel, maar per deel telt 1x: 2 delen x 0.50
    assert r.loc["P2", "Bedrag bewerkingen"] == pytest.approx(1.00)
    rij = calc.prijsopbouw.set_index("Code").loc["SawCut_Recht"]
    assert rij["Hoeveelheid"] == 6 and rij["Methode"] == "Per deel"  # P1 4 + P2 2 delen


@pytest.mark.parametrize("regel,verwacht", [("altijd", 25.0), ("nooit", 0.0), ("bij_zaagsneden", 0.0)])
def test_korten_regel_zonder_zaagsneden(profiel, regel, verwacht):
    xml = b"<R><Part Name='A' Width='30' Height='170' Length='1000'><Operations><Drill/></Operations></Part></R>"
    profiel.korten_regel = regel
    calc = bereken(lees_bestand("a.bvx", xml).onderdelen, profiel, {}, [(30, 170)])
    assert calc.stelkosten == verwacht


def test_profiel_validatie():
    with pytest.raises(ProfielFout):
        Prijsprofiel.van_dict({"naam": "x", "bewerkingen": {"Lap": {"prijs": -1}}})
    with pytest.raises(ProfielFout):
        Prijsprofiel.van_dict({"naam": "x", "bewerkingen": {"Lap": {"prijs": 1, "methode": "per_kilo"}}})
    with pytest.raises(ProfielFout):
        Prijsprofiel.van_dict({"bewerkingen": {}})


def test_profiel_roundtrip(profiel):
    assert Prijsprofiel.van_dict(profiel.naar_dict()) == profiel


# ---------- export ----------

def test_excel_export(resultaat, profiel):
    namen = laad_namen()
    calc = bereken(resultaat.onderdelen, profiel, namen, [(30, 170)])
    data = maak_excel(calc, namen, projectnaam="=HYPERLINK(1)", klant="Klant", referentie="R1",
                      profielnaam="Standaard", bestandsnaam="voorbeeld.bvx", sha256=resultaat.sha256,
                      versie="test", tolerantie=2.0, waarschuwingen=["let op"])
    wb = load_workbook(BytesIO(data))
    assert wb.sheetnames == ["Calculatie", "Prijsopbouw", "Info"]
    ws = wb["Calculatie"]
    assert ws["B1"].data_type == "s"  # geen formule-injectie
    assert ws.auto_filter.ref.startswith("A7:")
    totaalrij = [c.value for c in ws[ws.max_row]]
    assert totaalrij[0].startswith("TOTAAL")
    assert any(isinstance(v, str) and v.startswith("=SUBTOTAL(109,") for v in totaalrij)
    koppen = [c.value for c in ws[7]]
    assert "Recht afkorten" in koppen and "Pocket" in koppen
