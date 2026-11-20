# Changelog

## 2.0.3 (20-11-2026)
- Gebruiksteller: elke nieuw ingelezen upload wordt geregistreerd (tijdstip, versie, bestandstype,
  grootte, aantal regels/delen, SHA-256). Geen bestandsnaam, projectnaam of klantgegevens.

## 2.0.2 (17-11-2026)
- Onderaan de app: vergelijking met v1 (wat v1 voor hetzelfde bestand zou rekenen, per post en het verschil).

## 2.0.1 (17-11-2026)
Na test met echt bestand P250014 (358 onderdelen, 1.092 delen, 28 elementen):
- BvnMacro-bewerkingen worden geteld en gemeld (v1 negeerde er 145 in dit bestand).
- Element-kolom en -filter (attribuut Unit).
- Kopmatenlijst standaard leeg tot Heuvelman hem aanlevert (voorkwam ~€3.700 onterechte toeslag).
- README: oorzaak "Project onbekend" gecorrigeerd (niet verklaard door dit bestand).

## 2.0.0 (17-11-2026)
Eerste versie van v2, naast v1 gebouwd. Zie README voor de volledige lijst.
- Filters, totaalrij (app + Excel SUBTOTAAL), Nederlandse bewerkingsnamen, kopmatenlijst ±2 mm,
  prijzen per deel, invulbare projectnaam/klant/referentie.
- Klant-/prijsprofielen met import/export.
- Onbekende bewerkingen zichtbaar en gemeld; stelkosten korten volgens regel.
- Logo Heuvelman, Nederlandse bedragnotatie.
- Hygiene: defusedxml, validatie, wachtwoord, vastgezette versies, tests en CI.
- Opgelost: "Project onbekend" (truthiness-bug v1).
