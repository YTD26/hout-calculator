"""Excel-export: Calculatie (met filter + SUBTOTAAL-rij), Prijsopbouw en Info.

De totaalrij gebruikt SUBTOTAAL(109; ...): filtert de gebruiker in Excel
bijvoorbeeld de nullen weg, dan telt de totaalrij alleen de zichtbare regels.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .bewerkingen import weergavenaam
from .prijzen import Calculatie

BLAUW = "003366"
GEEL = "FFCC00"
EURO = '"€" #,##0.00'

KOP_FONT = Font(bold=True, color="FFFFFF")
KOP_VUL = PatternFill("solid", fgColor=BLAUW)
TOT_VUL = PatternFill("solid", fgColor=GEEL)
AFW_VUL = PatternFill("solid", fgColor="FFF4E5")
DUN = Side(style="thin", color="BBBBBB")

GEDEELDE_KOLOMMEN_SOM = {"Aantal", "Bewerkingen per deel", "Bewerkingen totaal", "Meters",
                         "Bedrag bewerkingen", "Bedrag toeslag", "Regeltotaal"}
EURO_KOLOMMEN = {"Bedrag bewerkingen", "Bedrag toeslag", "Regeltotaal"}


def _zet(ws, rij, kol, waarde):
    """Schrijft een cel en voorkomt formule-injectie vanuit het bronbestand:
    tekst die met '=' begint wordt als platte tekst opgeslagen, niet als formule."""
    if hasattr(waarde, "item"):  # numpy-getal -> Python-getal
        waarde = waarde.item()
    c = ws.cell(rij, kol, waarde)
    if isinstance(waarde, str) and waarde.startswith("="):
        c.data_type = "s"
    return c


def _breedtes(ws, minimaal=8, maximaal=40):
    for kol in ws.columns:
        lengte = max((len(str(c.value)) for c in kol if c.value is not None), default=0)
        ws.column_dimensions[get_column_letter(kol[0].column)].width = max(minimaal, min(lengte + 2, maximaal))


def maak_excel(calc: Calculatie, namen: dict[str, str], *, projectnaam: str, klant: str, referentie: str,
               profielnaam: str, bestandsnaam: str, sha256: str, versie: str, tolerantie: float,
               waarschuwingen: list[str], tijdstip: datetime | None = None) -> bytes:
    tijdstip = tijdstip or datetime.now()
    wb = Workbook()

    # ---------- Calculatie ----------
    ws = wb.active
    ws.title = "Calculatie"
    kop = [("Project", projectnaam), ("Klant", klant), ("Referentie", referentie),
           ("Prijsprofiel", profielnaam), ("Datum", tijdstip.strftime("%d-%m-%Y %H:%M"))]
    for r, (k, v) in enumerate(kop, start=1):
        ws.cell(r, 1, k).font = Font(bold=True, color=BLAUW)
        _zet(ws, r, 2, v)

    df = calc.regels.copy()
    weergave = {c: weergavenaam(c, namen) for c in calc.bewerkingscodes}
    df = df.rename(columns=weergave)
    kolommen = list(df.columns)
    bewerkingskolommen = set(weergave.values())

    kop_rij = len(kop) + 2
    eerste = kop_rij + 1
    laatste = kop_rij + len(df)
    for j, naam in enumerate(kolommen, start=1):
        c = ws.cell(kop_rij, j, naam)
        c.font, c.fill = KOP_FONT, KOP_VUL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for i, rij in enumerate(df.itertuples(index=False), start=eerste):
        afwijkend = getattr(rij, "Toeslag", "") != ""
        for j, waarde in enumerate(rij, start=1):
            c = _zet(ws, i, j, waarde)
            if kolommen[j - 1] in EURO_KOLOMMEN:
                c.number_format = EURO
            if afwijkend:
                c.fill = AFW_VUL

    # Totaalrij met SUBTOTAAL zodat Excel-filters meegenomen worden
    tot = laatste + 1
    ws.cell(tot, 1, "TOTAAL (zichtbare regels)")
    for j, naam in enumerate(kolommen, start=1):
        if naam in GEDEELDE_KOLOMMEN_SOM or naam in bewerkingskolommen:
            L = get_column_letter(j)
            c = ws.cell(tot, j, f"=SUBTOTAL(109,{L}{eerste}:{L}{laatste})")
            if naam in EURO_KOLOMMEN:
                c.number_format = EURO
    for j in range(1, len(kolommen) + 1):
        c = ws.cell(tot, j)
        c.font, c.fill, c.border = Font(bold=True, color=BLAUW), TOT_VUL, Border(top=DUN)

    ws.auto_filter.ref = f"A{kop_rij}:{get_column_letter(len(kolommen))}{laatste}"
    ws.freeze_panes = ws.cell(eerste, 2)
    _breedtes(ws)
    ws.column_dimensions["A"].width = 26

    # ---------- Prijsopbouw ----------
    wp = wb.create_sheet("Prijsopbouw")
    po = calc.prijsopbouw
    for j, naam in enumerate(po.columns, start=1):
        c = wp.cell(1, j, naam)
        c.font, c.fill = KOP_FONT, KOP_VUL
    for i, rij in enumerate(po.itertuples(index=False), start=2):
        for j, waarde in enumerate(rij, start=1):
            c = _zet(wp, i, j, waarde)
            if po.columns[j - 1] in ("Prijs", "Bedrag"):
                c.number_format = EURO
    t = len(po) + 2
    wp.cell(t, 1, "TOTAAL excl. BTW").font = Font(bold=True)
    bedrag_kol = get_column_letter(list(po.columns).index("Bedrag") + 1)
    c = wp.cell(t, list(po.columns).index("Bedrag") + 1,
                f"=SUM({bedrag_kol}2:{bedrag_kol}{t - 1})" if len(po) else 0)
    c.number_format, c.font = EURO, Font(bold=True)
    for j in range(1, len(po.columns) + 1):
        wp.cell(t, j).fill = TOT_VUL
    _breedtes(wp)

    # ---------- Info (herleidbaarheid) ----------
    wi = wb.create_sheet("Info")
    info = [("App-versie", versie), ("Bronbestand", bestandsnaam), ("SHA-256 bronbestand", sha256),
            ("Berekend op", tijdstip.strftime("%d-%m-%Y %H:%M:%S")), ("Prijsprofiel", profielnaam),
            ("Kopmaat-tolerantie (mm)", tolerantie), ("Totaal excl. BTW (app)", calc.totaal)]
    if calc.zonder_prijs:
        info.append(("Bewerkingen zonder prijs", ", ".join(calc.zonder_prijs)))
    for r, (k, v) in enumerate(info, start=1):
        wi.cell(r, 1, k).font = Font(bold=True)
        _zet(wi, r, 2, v)
    if waarschuwingen:
        r = len(info) + 2
        wi.cell(r, 1, "Waarschuwingen bij inlezen").font = Font(bold=True)
        for k, w in enumerate(waarschuwingen, start=r + 1):
            _zet(wi, k, 1, w)
    _breedtes(wi, maximaal=80)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
