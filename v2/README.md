# Heuvelman Hout Calculator v2

Nieuwe versie van de calculatietool, gebouwd naast v1. v1 (`app.py` in de root, branch `main`)
blijft ongewijzigd en blijft draaien.

## Starten

```bash
cd v2
pip install -r requirements-dev.txt
python -m pytest -q             # 34 tests
cd .. && streamlit run v2/app.py
```

### Deployen op Streamlit Community Cloud (als tweede app)
1. *Create app*, kies repo `YTD26/hout-calculator`, branch `v2`, main file `v2/app.py`.
2. *Advanced settings* > Secrets: plak de inhoud van `secrets.toml.voorbeeld` met een eigen wachtwoord.
   Zonder `APP_WACHTWOORD` is de app (en daarmee de prijzen) openbaar bereikbaar.

## Wat er nieuw is ten opzichte van v1

| Verzoek Heuvelman (17-11-2026) | Oplossing in v2 |
|---|---|
| Filteroptie | Filters op: lege bewerkingskolommen verbergen, alleen delen met bewerkingen, per bewerking, kopmaat, zoeken op positie/kwaliteit. Excel heeft filters op alle kolomkoppen. |
| Totaalrij | Gele totaalrij over de zichtbare regels in de app; in Excel een `SUBTOTAAL`-rij die meetelt met het Excel-filter. |
| Nederlandse namen | Vertaaltabel `config/bewerkingen.json`, ook aan te passen in de zijbalk. **Namen zijn concept.** |
| Afwijkende maat | Alleen afwijkend buiten de standaard netto kopmatenlijst ± 2 mm (instelbaar), liggend/staand maakt niet uit. Lijst in `config/kopmaten.csv`, te importeren in de zijbalk. **Lijst is leeg tot Heuvelman hem aanlevert**: dan wordt er niets als afwijkend gerekend (met melding). |
| Prijzen per deel | Per bewerking kies je *per stuk* of *per deel*, vastgelegd in een klant-/prijsprofiel. |
| Projectnaam | Projectnaam, klant en referentie zijn invulbaar (vooringevuld uit het bestand) en komen in de Excel. |

Daarnaast:
- **Geen stille fouten meer:** onbekende Hundegger-bewerkingen worden geteld, getoond en gemeld als ze
  geen prijs hebben. Dat geldt ook voor `BvnMacro`-bewerkingen: in testbestand P250014 staan er 145
  (macro 0402) die v1 stil negeerde. Wat macro 0402 is en of hij geprijsd moet worden, moet Heuvelman bevestigen.
- **Element-kolom en -filter** (attribuut `Unit`, bv. BU-001) zodat per wand-/dakelement bekeken kan worden.
- **Stelkosten korten** standaard alleen als er zaagsneden zijn (instelbaar: altijd / bij zaagsneden / nooit).
- **Schaven en afwijkende maat zijn gescheiden.** Er is een aparte toeslag per m1 voor elk, zonder dubbeltelling.
- Excel met tabbladen *Calculatie*, *Prijsopbouw* (sluit aan op het totaal) en *Info*
  (app-versie, bestandsnaam, SHA-256 van het bronbestand, tijdstip, profiel, waarschuwingen).

### Projectnaam
Getest met P250014 (Vertex BD-export): de projectnaam staat alleen in het commentaar `<!-- project: ... -->`
en daar vinden v1 én v2 hem. Waarom Heuvelman "Project onbekend" ziet, is met dit bestand dus niet verklaard:
waarschijnlijk komt het bij bestanden van andere aanleveraars voor (bijv. hsbCAD). Stuur zo'n bestand mee om
dat te bevestigen. v2 zoekt breder (Job/Project-attributen, commentaar met spaties) en de naam is altijd
handmatig aan te passen. Daarnaast is in v2 een `if element:`-truthiness-fout uit v1 opgelost.

## Hygiene
- XML via `defusedxml` (bescherming tegen XXE / entity-expansie), maximaal 20 MB, BOM-tolerant.
- Validatie per onderdeel (aantal, maten) met waarschuwingen in plaats van crashes of stille nullen.
- Validatie van prijsprofielen (geen negatieve prijzen, alleen bekende methodes).
- Optioneel wachtwoord (`APP_WACHTWOORD`) met constant-time vergelijking.
- Geen stacktraces naar gebruikers (`showErrorDetails = false`). Fouten gaan naar de log.
- Excel: tekst uit het bronbestand die met `=` begint wordt als tekst opgeslagen (geen formule-injectie).
- Vastgezette versies van alle packages, unit- en rooktests, GitHub Actions-workflow `v2-tests`.
- Rekenkern (`houtcalc/`) staat los van de interface. Te hergebruiken als dit naar TABS/In2CRM gaat.
- OCR/Perplexity uit v1 zit bewust **niet** in v2: dat stuurde klantgegevens naar een externe AI-dienst.

## Aannames die Heuvelman moet bevestigen
1. **Nederlandse namen** van de bewerkingen (`config/bewerkingen.json`), met name `Neig` en `HipRidgeCut`.
2. **Standaard netto kopmatenlijst** (`config/kopmaten.csv`). Tolerantie ±2 mm geldt op dikte én breedte.
3. **Per deel**: geïnterpreteerd als *per bewerkingstype*. Een deel met 2x boren en 1x keep telt
   bij "per deel" 1x boren en 1x keep. Is het juist één prijs per deel ongeacht de bewerkingen, dan is dat een kleine aanpassing.
4. **Schaven**: schaafcode (G10-1/G10-5/GESCHAAFD) bij een standaard kopmaat geeft de schaaftoeslag. Bij een
   afwijkende maat geldt alleen de afwijkende-maat toeslag (geen dubbele toeslag).
5. **Dikte = `Width`, Breedte = `Height`**: klopt met P250014 (38x235, 38x140, ...).
6. **HMM** wordt nog niet ingelezen. **HMLX** wordt als XML gelezen. Beide controleren met voorbeeldbestanden.
7. **Macro 0402** (`BvnMacro`): betekenis en prijs.
8. Prijsprofielen leven per sessie. Bewaren gaat via export/import (.json) of door het bestand in
   `config/profielen/` te zetten. Een gedeelde opslag (database) is een volgende stap.

## Structuur
```
v2/
  app.py                  Streamlit-interface
  houtcalc/               rekenkern (parser, bewerkingen, kopmaten, prijzen, export)
  config/                 bewerkingsnamen, kopmatenlijst, prijsprofielen
  assets/                 logo
  tests/                  pytest (data/voorbeeld.bvx is synthetisch, geen klantorder)
```
