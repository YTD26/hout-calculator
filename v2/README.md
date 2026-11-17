# Heuvelman Hout Calculator v2

Nieuwe versie van de calculatietool, gebouwd naast v1. v1 (`app.py` in de root, branch `main`)
blijft ongewijzigd en blijft draaien.

## Starten

```bash
cd v2
pip install -r requirements-dev.txt
python -m pytest -q             # 33 tests
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
| Afwijkende maat | Alleen afwijkend buiten de standaard netto kopmatenlijst ± 2 mm (instelbaar), liggend/staand maakt niet uit. Lijst in `config/kopmaten.csv`, te importeren in de zijbalk. **Lijst bevat nu alleen het voorbeeld 30x170.** |
| Prijzen per deel | Per bewerking kies je *per stuk* of *per deel*, vastgelegd in een klant-/prijsprofiel. |
| Projectnaam | Bug uit v1 opgelost (zie hieronder) en projectnaam, klant en referentie zijn invulbaar. Ze komen in de Excel. |

Daarnaast:
- **Geen stille fouten meer:** onbekende Hundegger-bewerkingen (bv. `Pocket`, `Tenon`) worden geteld,
  getoond en gemeld als ze geen prijs hebben. v1 liet ze weg en rekende €0.
- **Stelkosten korten** standaard alleen als er zaagsneden zijn (instelbaar: altijd / bij zaagsneden / nooit).
- **Schaven en afwijkende maat zijn gescheiden.** Er is een aparte toeslag per m1 voor elk, zonder dubbeltelling.
- Excel met tabbladen *Calculatie*, *Prijsopbouw* (sluit aan op het totaal) en *Info*
  (app-versie, bestandsnaam, SHA-256 van het bronbestand, tijdstip, profiel, waarschuwingen).

### Bug "Project onbekend" in v1
v1 deed `if job_node:`. Een XML-element zonder kindelementen is in Python *falsy*, dus
`<Job Project="..."/>` gaf altijd "Onbekend". v2 gebruikt `is not None` en probeert meerdere attributen.

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
5. **Dikte = `Width`, Breedte = `Height`** uit het BVX-bestand (overgenomen uit v1, nog te controleren met echte bestanden).
6. **HMM** wordt nog niet ingelezen. **HMLX** wordt als XML gelezen. Beide controleren met voorbeeldbestanden.
7. Prijsprofielen leven per sessie. Bewaren gaat via export/import (.json) of door het bestand in
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
