"""Heuvelman Hout Calculator v2 - Streamlit-interface.

Alle reken- en inleeslogica zit in het pakket `houtcalc` (los testbaar).
Starten:  streamlit run v2/app.py
"""

from __future__ import annotations

import hmac
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from houtcalc import __version__
from houtcalc import kopmaten as km
from houtcalc.bewerkingen import laad_namen, weergavenaam
from houtcalc.export import maak_excel
from houtcalc.parser import ALLE_EXTENSIES, BestandFout, MAX_BESTANDSGROOTTE, lees_bestand
from houtcalc.prijzen import (KORTEN_REGELS, METHODES, Prijsprofiel, ProfielFout, bereken,
                              laad_profielen)

HIER = Path(__file__).resolve().parent
LOGO = HIER / "assets" / "heuvelman_logo.png"
BLAUW, GEEL = "#003366", "#FFCC00"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("houtcalc")

st.set_page_config(page_title="Heuvelman Hout Calculator", page_icon=str(LOGO), layout="wide")

st.markdown(f"""
<style>
h1, h2, h3 {{ color: {BLAUW} !important; }}
div.stButton > button, div.stDownloadButton > button {{
    background-color: {GEEL}; color: {BLAUW}; border: none; font-weight: 700;
}}
div.stButton > button:hover, div.stDownloadButton > button:hover {{ background-color: #E6B800; color: {BLAUW}; }}
[data-testid="stFileUploader"] section {{ border: 2px dashed {BLAUW}; background-color: #F4F8FB; }}
[data-testid="stMetricValue"] {{ color: {BLAUW}; }}
.versie {{ color: #8899aa; font-size: 0.8rem; }}
</style>
""", unsafe_allow_html=True)


# =====================================================================
# Toegang (optioneel wachtwoord via st.secrets["APP_WACHTWOORD"])
# =====================================================================

def _wachtwoord() -> str | None:
    try:
        return st.secrets.get("APP_WACHTWOORD")
    except Exception:  # geen secrets.toml aanwezig
        return None


def toegang_ok() -> bool:
    verwacht = _wachtwoord()
    if not verwacht or st.session_state.get("ingelogd"):
        return True
    st.image(str(LOGO), width=260)
    st.subheader("Inloggen")
    with st.form("login"):
        invoer = st.text_input("Wachtwoord", type="password")
        if st.form_submit_button("Inloggen"):
            if hmac.compare_digest(invoer.encode(), str(verwacht).encode()):
                st.session_state.ingelogd = True
                st.rerun()
            st.error("Onjuist wachtwoord.")
    return False


if not toegang_ok():
    st.stop()


# =====================================================================
# Sessie-initialisatie
# =====================================================================

def init_state():
    ss = st.session_state
    if "profielen" not in ss:
        try:
            ss.profielen = laad_profielen()
        except ProfielFout as e:
            st.error(f"Standaard prijsprofiel kon niet geladen worden: {e}")
            st.stop()
        ss.actief_profiel = "Standaard" if "Standaard" in ss.profielen else next(iter(ss.profielen))
    ss.setdefault("kopmaten", km.laad_standaard())
    ss.setdefault("tolerantie", km.STANDAARD_TOLERANTIE_MM)
    ss.setdefault("namen", laad_namen())
    ss.setdefault("editor_versie", 0)


init_state()
ss = st.session_state


def euro(v) -> str:
    """Nederlandse notatie: € 1.234,56"""
    return "€ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def getal(v) -> str:
    return f"{v:g}".replace(".", ",")


@st.cache_data(show_spinner="Bestand inlezen...", max_entries=20)
def parse(naam: str, data: bytes):
    return lees_bestand(naam, data)


# =====================================================================
# Kop
# =====================================================================

st.logo(str(LOGO), size="large")
kop_l, kop_r = st.columns([1, 4], vertical_alignment="center")
kop_l.image(str(LOGO), width=220)
kop_r.title("Calculatie Tool")
kop_r.markdown("Upload een Hundegger-productiebestand (BVX) voor een directe calculatie van bewerkingen, "
               "toeslagen en stelkosten.")

bestand = st.file_uploader("Sleep bestand hierheen", type=ALLE_EXTENSIES,
                           help=f"BVX/XML/HMLX, maximaal {MAX_BESTANDSGROOTTE // (1024 * 1024)} MB. "
                                "HMM volgt zodra er een voorbeeldbestand is.")

resultaat = None
if bestand is not None:
    try:
        resultaat = parse(bestand.name, bestand.getvalue())
        if ss.get("laatste_bestand") != resultaat.sha256:
            # Nieuw bestand: tabellen in de zijbalk opnieuw opbouwen (andere bewerkingen mogelijk)
            ss.laatste_bestand = resultaat.sha256
            ss.editor_versie += 1
            log.info("Ingelezen: %s (%d onderdelen, sha256 %s)", bestand.name, len(resultaat.onderdelen),
                     resultaat.sha256[:12])
    except BestandFout as e:
        st.error(str(e))
    except Exception:
        log.exception("Onverwachte fout bij inlezen van %s", bestand.name)
        st.error("Er ging iets onverwachts mis bij het inlezen. Het bestand is niet verwerkt; "
                 "neem contact op met de beheerder en stuur het bestand mee.")

gevonden_codes: list[str] = []
if resultaat:
    for o in resultaat.onderdelen:
        for c in o.bewerkingen:
            if c not in gevonden_codes:
                gevonden_codes.append(c)


# =====================================================================
# Zijbalk: profielen, prijzen, kopmaten, namen
# =====================================================================

def profiel() -> Prijsprofiel:
    return ss.profielen[ss.actief_profiel]


with st.sidebar:
    st.header("Instellingen")

    # ---------- Klantprofiel ----------
    with st.expander("Klant-/prijsprofiel", expanded=True):
        namen_profielen = list(ss.profielen)
        ss.actief_profiel = st.selectbox("Actief profiel", namen_profielen,
                                         index=namen_profielen.index(ss.actief_profiel))
        nieuw = st.text_input("Nieuw profiel (kopie van actief)", placeholder="bijv. Linex")
        if st.button("Profiel aanmaken", disabled=not nieuw.strip()):
            if nieuw.strip() in ss.profielen:
                st.warning("Er bestaat al een profiel met die naam.")
            else:
                d = profiel().naar_dict()
                d["naam"] = nieuw.strip()
                ss.profielen[nieuw.strip()] = Prijsprofiel.van_dict(d)
                ss.actief_profiel = nieuw.strip()
                ss.editor_versie += 1
                st.rerun()

        geupload = st.file_uploader("Profiel importeren (.json)", type=["json"], key="profiel_upload")
        if geupload is not None and st.button("Importeren"):
            try:
                p = Prijsprofiel.van_dict(json.loads(geupload.getvalue().decode("utf-8")))
                ss.profielen[p.naam] = p
                ss.actief_profiel = p.naam
                ss.editor_versie += 1
                st.rerun()
            except (ProfielFout, json.JSONDecodeError, UnicodeDecodeError) as e:
                st.error(f"Profiel niet geïmporteerd: {e}")

        st.download_button("Profiel exporteren (.json)", profiel().naar_json(),
                           file_name=f"prijsprofiel_{re.sub(r'[^A-Za-z0-9_-]+', '_', ss.actief_profiel)}.json",
                           mime="application/json", width="stretch")
        st.caption("Wijzigingen gelden voor deze sessie. Exporteer het profiel om het te bewaren.")

    # ---------- Prijzen bewerkingen ----------
    with st.expander("Prijzen bewerkingen", expanded=False):
        p = profiel()
        codes = list(p.bewerkingen) + [c for c in gevonden_codes if c not in p.bewerkingen]
        prijs_df = pd.DataFrame([{
            "Code": c,
            "Bewerking": weergavenaam(c, ss.namen),
            "Prijs": p.bewerkingen[c].prijs if c in p.bewerkingen else None,
            "Methode": METHODES[p.bewerkingen[c].methode] if c in p.bewerkingen else METHODES["per_stuk"],
        } for c in codes])
        bewerkt = st.data_editor(
            prijs_df, hide_index=True, width="stretch",
            key=f"prijzen_{ss.actief_profiel}_{ss.editor_versie}",
            disabled=["Code", "Bewerking"],
            column_config={
                "Code": None,
                "Prijs": st.column_config.NumberColumn("Prijs (€)", min_value=0.0, step=0.05, format="%.2f"),
                "Methode": st.column_config.SelectboxColumn(options=list(METHODES.values()), required=True),
            },
        )
        st.caption("**Per stuk**: prijs × aantal keer × aantal delen. **Per deel**: prijs × aantal delen "
                   "met deze bewerking. Lege prijs = bewerking wordt niet geprijsd.")
        terug = {v: k for k, v in METHODES.items()}
        d = p.naar_dict()
        d["bewerkingen"] = {r.Code: {"prijs": float(r.Prijs), "methode": terug[r.Methode]}
                            for r in bewerkt.itertuples() if pd.notna(r.Prijs)}

    # ---------- Toeslagen & stelkosten ----------
    with st.expander("Toeslagen & stelkosten", expanded=False):
        k = f"{ss.actief_profiel}_{ss.editor_versie}"
        d["toeslagen"]["afwijkende_maat_m1"] = st.number_input(
            "Toeslag afwijkende maat (€/m1)", min_value=0.0, step=0.05, format="%.2f",
            value=float(p.toeslag_afwijkende_maat_m1), key=f"ta_{k}")
        d["toeslagen"]["schaven_m1"] = st.number_input(
            "Toeslag schaven volgens code (€/m1)", min_value=0.0, step=0.05, format="%.2f",
            value=float(p.toeslag_schaven_m1), key=f"ts_{k}")
        d["schaafcodes"] = [c for c in st.text_input(
            "Schaafcodes (kommagescheiden)", value=", ".join(p.schaafcodes), key=f"sc_{k}").split(",") if c.strip()]
        d["stelkosten"]["schaven"] = st.number_input(
            "Stelkosten schaven (€ per order)", min_value=0.0, step=5.0, format="%.2f",
            value=float(p.stelkosten_schaven), key=f"ss_{k}")
        d["stelkosten"]["korten"] = st.number_input(
            "Stelkosten korten (€ per order)", min_value=0.0, step=5.0, format="%.2f",
            value=float(p.stelkosten_korten), key=f"sk_{k}")
        regels = list(KORTEN_REGELS)
        d["stelkosten"]["korten_regel"] = st.selectbox(
            "Stelkosten korten rekenen", regels, index=regels.index(p.korten_regel),
            format_func=KORTEN_REGELS.get, key=f"kr_{k}")

    try:
        ss.profielen[ss.actief_profiel] = Prijsprofiel.van_dict(d)
    except ProfielFout as e:
        st.error(f"Profiel ongeldig, wijziging niet toegepast: {e}")

    # ---------- Kopmaten ----------
    with st.expander("Standaard netto kopmaten", expanded=False):
        ss.tolerantie = st.number_input("Tolerantie (± mm)", min_value=0.0, max_value=10.0, step=0.5,
                                        value=float(ss.tolerantie))
        kop_df = st.data_editor(
            pd.DataFrame(ss.kopmaten, columns=["Dikte", "Breedte"]), num_rows="dynamic",
            hide_index=True, width="stretch", key=f"kopmaten_{ss.editor_versie}",
            column_config={"Dikte": st.column_config.NumberColumn(min_value=1.0, format="%g"),
                           "Breedte": st.column_config.NumberColumn(min_value=1.0, format="%g")})
        ss.kopmaten = sorted({(float(r.Dikte), float(r.Breedte)) for r in kop_df.itertuples()
                              if pd.notna(r.Dikte) and pd.notna(r.Breedte) and r.Dikte > 0 and r.Breedte > 0})
        csv_upload = st.file_uploader("Kopmatenlijst importeren (.csv: dikte;breedte)", type=["csv"],
                                      key="kopmaten_upload")
        if csv_upload is not None and st.button("Lijst vervangen"):
            maten = km.lees_csv(csv_upload.getvalue().decode("utf-8-sig", errors="replace"))
            if maten:
                ss.kopmaten = maten
                ss.editor_versie += 1
                st.rerun()
            st.error("Geen geldige maten gevonden in het bestand.")
        st.download_button("Kopmatenlijst exporteren (.csv)", km.naar_csv(ss.kopmaten),
                           file_name="kopmaten.csv", mime="text/csv", width="stretch")

    # ---------- Bewerkingsnamen ----------
    with st.expander("Namen van bewerkingen", expanded=False):
        alle = list(dict.fromkeys(list(ss.namen) + gevonden_codes))
        namen_df = st.data_editor(
            pd.DataFrame([{"Code": c, "Naam": ss.namen.get(c, c)} for c in alle]),
            hide_index=True, width="stretch", disabled=["Code"], key=f"namen_{ss.editor_versie}")
        ss.namen = {r.Code: (str(r.Naam).strip() or r.Code) for r in namen_df.itertuples()}
        st.download_button(
            "Namen exporteren (.json)",
            json.dumps({"bewerkingen": {c: {"naam": n} for c, n in ss.namen.items()}}, indent=2, ensure_ascii=False),
            file_name="bewerkingen.json", mime="application/json", width="stretch")
        st.caption("Leg vaste namen vast door dit bestand in config/bewerkingen.json te zetten.")

    st.markdown(f"<div class='versie'>Versie {__version__}</div>", unsafe_allow_html=True)


# =====================================================================
# Hoofdscherm
# =====================================================================

if resultaat is None:
    st.info("Nog geen bestand geladen. De prijsinstellingen staan in de zijbalk.")
    st.stop()

calc = bereken(resultaat.onderdelen, profiel(), ss.namen, ss.kopmaten, ss.tolerantie)
namen_kol = {c: weergavenaam(c, ss.namen) for c in calc.bewerkingscodes}

# ---------- Projectgegevens ----------
st.subheader("Projectgegevens")
p1, p2, p3 = st.columns(3)
fk = resultaat.sha256[:12]
projectnaam = p1.text_input("Projectnaam", value=resultaat.projectnaam, key=f"proj_{fk}",
                            placeholder="Niet gevonden in bestand, vul zelf in").strip()
klant = p2.text_input("Klant", value="" if ss.actief_profiel == "Standaard" else ss.actief_profiel,
                      key=f"klant_{fk}_{ss.actief_profiel}").strip()
referentie = p3.text_input("Referentie / ordernummer", key=f"ref_{fk}").strip()

# ---------- Meldingen ----------
if calc.zonder_prijs:
    st.warning("Bewerkingen in dit bestand **zonder prijs** in profiel '" + ss.actief_profiel + "': "
               + ", ".join(namen_kol[c] for c in calc.zonder_prijs)
               + ". Ze zijn wel geteld, maar niet geprijsd. Vul een prijs in via *Prijzen bewerkingen*.")
if not ss.kopmaten:
    st.warning("Er is geen standaard kopmatenlijst ingesteld: afwijkende maten kunnen niet beoordeeld worden.")
elif len(ss.kopmaten) < 3:
    st.info(f"De kopmatenlijst bevat nu {len(ss.kopmaten)} maat/maten. Vul de lijst aan via de zijbalk, "
            "anders worden veel maten als afwijkend gezien.")
if resultaat.waarschuwingen:
    with st.expander(f"⚠️ {len(resultaat.waarschuwingen)} waarschuwing(en) bij inlezen"):
        for w in resultaat.waarschuwingen:
            st.write("• " + w)

# ---------- Kerncijfers ----------
r = calc.regels
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Delen", f"{int(r['Aantal'].sum()):,}".replace(",", "."))
m2.metric("Bewerkingen totaal", f"{int(r['Bewerkingen totaal'].sum()):,}".replace(",", "."))
m3.metric("Regels met toeslag", int((r["Toeslag"] != "").sum()))
m4.metric("Stelkosten", euro(calc.stelkosten))
m5.metric("Totaal excl. BTW", euro(calc.totaal))

tab_onderdelen, tab_prijs = st.tabs(["Onderdelen & bewerkingen", "Prijsopbouw"])

with tab_onderdelen:
    f1, f2, f3, f4 = st.columns([1.2, 2, 1, 1.5])
    verberg_leeg = f1.toggle("Verberg 0-kolommen", value=True,
                             help="Bewerkingskolommen die in de selectie overal 0 zijn verbergen")
    alleen_met_bew = f1.toggle("Alleen delen met bewerkingen", value=False)
    filter_bew = f2.multiselect("Alleen delen met bewerking", calc.bewerkingscodes, format_func=namen_kol.get,
                                placeholder="Kies een of meer bewerkingen")
    filter_kop = f3.selectbox("Kopmaat", ["Alle", km.STANDAARD, km.AFWIJKEND, km.ONBEKEND])
    zoek = f4.text_input("Zoek positie / kwaliteit")

    zicht = r.copy()
    if alleen_met_bew:
        zicht = zicht[zicht["Bewerkingen per deel"] > 0]
    for c in filter_bew:
        zicht = zicht[zicht[c] > 0]
    if filter_kop != "Alle":
        zicht = zicht[zicht["Kopmaat"] == filter_kop]
    if zoek:
        zoek_l = zoek.lower()
        zicht = zicht[zicht["Positie"].str.lower().str.contains(zoek_l, regex=False)
                      | zicht["Kwaliteit"].str.lower().str.contains(zoek_l, regex=False)]

    bew_kol = [c for c in calc.bewerkingscodes if not (verberg_leeg and zicht[c].sum() == 0)]
    kolommen = (["Positie", "Aantal", "Dikte", "Breedte", "Lengte (mm)", "Kwaliteit"] + bew_kol
                + ["Bewerkingen per deel", "Bewerkingen totaal", "Kopmaat", "Toeslag", "Meters",
                   "Bedrag bewerkingen", "Bedrag toeslag", "Regeltotaal"])
    tabel = zicht[kolommen].rename(columns=namen_kol)
    # Maten als tekst, zodat de totaalrij daar leeg kan blijven (Streamlit toont lege getallen als 'None')
    for kol in ("Dikte", "Breedte"):
        tabel[kol] = tabel[kol].map(getal)
    tabel["Lengte (mm)"] = tabel["Lengte (mm)"].map(lambda v: f"{v:.0f}")

    # Totaalrij over de zichtbare regels
    som_kol = ["Aantal", "Bewerkingen per deel", "Bewerkingen totaal", "Meters", "Bedrag bewerkingen",
               "Bedrag toeslag", "Regeltotaal"] + [namen_kol[c] for c in bew_kol]
    totaal = {c: (tabel[c].sum() if c in som_kol else None) for c in tabel.columns}
    totaal.update({k: "" for k in ("Dikte", "Breedte", "Lengte (mm)", "Kwaliteit", "Kopmaat", "Toeslag")})
    totaal["Positie"] = f"TOTAAL ({len(tabel)} regels)"
    tabel_met_totaal = pd.concat([tabel, pd.DataFrame([totaal])], ignore_index=True)

    def kleur(rij):
        if str(rij["Positie"]).startswith("TOTAAL"):
            return [f"background-color: {GEEL}; font-weight: bold"] * len(rij)
        if rij["Toeslag"]:
            return ["background-color: #fff4e5"] * len(rij)
        return [""] * len(rij)

    def leeg_veilig(fn):
        return lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else fn(v)

    opmaak = {c: leeg_veilig(euro) for c in ("Bedrag bewerkingen", "Bedrag toeslag", "Regeltotaal")}
    opmaak.update({"Meters": leeg_veilig(lambda v: f"{v:.2f}".replace(".", ",")),
                   })
    rechts = {k: st.column_config.TextColumn(k, alignment="right") for k in ("Dikte", "Breedte", "Lengte (mm)")}
    st.dataframe(
        tabel_met_totaal.style.apply(kleur, axis=1).format(opmaak, na_rep=""),
        width="stretch", hide_index=True,
        height=min(3 + 35 * (len(tabel_met_totaal) + 1), 640), column_config=rechts,
    )
    st.caption(f"{len(tabel)} van {len(r)} regels zichtbaar. Oranje = regel met toeslag "
               f"(afwijkende kopmaat buiten ±{ss.tolerantie:g} mm, of schaafcode).")

with tab_prijs:
    st.dataframe(calc.prijsopbouw.drop(columns=["Code"]).style.format(
                     {"Prijs": euro, "Bedrag": euro, "Hoeveelheid": lambda v: getal(round(v, 3))}),
                 width="stretch", hide_index=True)
    st.markdown(f"**Totaal excl. BTW: {euro(calc.totaal)}**")

# ---------- Export ----------
st.divider()
excel = maak_excel(calc, ss.namen, projectnaam=projectnaam or "Onbekend", klant=klant, referentie=referentie,
                   profielnaam=ss.actief_profiel, bestandsnaam=bestand.name, sha256=resultaat.sha256,
                   versie=__version__, tolerantie=ss.tolerantie, waarschuwingen=resultaat.waarschuwingen,
                   tijdstip=datetime.now())
veilig = re.sub(r"[^A-Za-z0-9_-]+", "_", projectnaam or Path(bestand.name).stem).strip("_") or "calculatie"
st.download_button("📥 Download calculatie (Excel)", excel, file_name=f"calculatie_{veilig}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.caption("De Excel bevat alle regels met filters op de kolomkoppen en een totaalrij die alleen de "
           "zichtbare (gefilterde) regels optelt, plus tabbladen Prijsopbouw en Info.")
