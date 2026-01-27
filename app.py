import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# --- CONFIGURATIE: PRIJSLIJST 2026 (Q1) ---
# Structuur: 'TagNaam': {'naam': 'NL Omschrijving', 'basis': prijs_st, 'bulk': prijs_vanaf_50}
# Pas de 'keys' (links) aan als jouw machine andere Engelse termen gebruikt.

PRICING_MODEL = {
    # Keeps / Uitsparingen (Standaard ingesteld op < 50mm prijs)
    "Slot":         {'naam': "Keep kopse kant (< 50mm)", 'basis': 1.90, 'bulk': 1.70},
    "LapJoin":      {'naam': "Keep midden (< 50mm)",     'basis': 3.75, 'bulk': 3.50},
    "Recess":       {'naam': "Keep midden (> 50mm)",     'basis': 4.25, 'bulk': 4.00}, # Voorbeeld mapping
    
    # Zaagbewerkingen
    "Saw":          {'naam': "Schuine kant per snede",   'basis': 0.90, 'bulk': 0.75},
    "Cut":          {'naam': "Schuine kant per snede",   'basis': 0.90, 'bulk': 0.75}, # Alternatieve tag
    "Bevel":        {'naam': "Neigen per snede",         'basis': 1.50, 'bulk': 1.25},
    
    # Boren
    "Drill":        {'naam': "Gaten boren (6-25mm)",     'basis': 0.95, 'bulk': 0.85},
    "DrillGroup":   {'naam': "Gaten + indoppen",         'basis': 2.70, 'bulk': 2.50},
    
    # Overig
    "VentSlot":     {'naam': "Ventilatiesleuven",        'basis': 0.25, 'bulk': 0.22},
    "Mark":         {'naam': "Markering (optioneel)",    'basis': 0.00, 'bulk': 0.00},
    
    # Fallback voor onbekende tags
    "Default":      {'naam': "Overige bewerking",        'basis': 0.00, 'bulk': 0.00}
}

STARTUP_FEE = 20.00
BULK_THRESHOLD = 49

st.set_page_config(page_title="Hout Calculator 2026", page_icon="🌲")

st.title("🌲 Houtbewerking Calculator")
st.markdown("""
**Prijslijst:** Q1 2026  
**Regels:** Staffelkorting bij > 49 stuks per bewerking. Starttarief €20,00 bij kleine orders.
""")

# File Uploader
uploaded_file = st.file_uploader("Sleep je .bvx bestand hierheen", type=['bvx', 'xml', 'hmm'])

if uploaded_file is not None:
    content = uploaded_file.getvalue().decode("utf-8", errors='ignore')
    
    operations = []
    try:
        root = ET.fromstring(content)
        # Filter tags die geen bewerking zijn
        ignore_list = ['BVX', 'Project', 'Header', 'Version', 'Timestamp', 'Cost', 'Description', 'Geometry', 'Name']
        
        for elem in root.iter():
            # We filteren op tags die lijken op bewerkingen
            if elem.tag not in ignore_list and len(elem.tag) > 2:
                operations.append(elem.tag)
                
    except ET.ParseError:
        st.error("⚠️ Dit bestand is geen geldige XML.")
        st.stop()

    if not operations:
        st.warning("Geen bewerkingen gevonden.")
        st.stop()

    # Tellen
    counts = pd.Series(operations).value_counts().to_dict()
    
    data_rows = []
    total_parts_cost = 0.0
    total_count = sum(counts.values())

    # Berekening per regel
    for op, count in counts.items():
        # Zoek de juiste prijsregel
        rule = PRICING_MODEL.get(op)
        
        # Als exacte tag niet bestaat, zoek op gedeeltelijke match (bijv "Saw" in "SawCut")
        if not rule:
            match_found = False
            for key, val in PRICING_MODEL.items():
                if key in op:
                    rule = val
                    match_found = True
                    break
            if not match_found:
                rule = PRICING_MODEL["Default"]

        # Staffelkorting logica
        # De prijslijst zegt: prijs p/st bij > 49 stuks.
        # Dit passen we toe per bewerkingstype.
        is_bulk = count > BULK_THRESHOLD
        unit_price = rule['bulk'] if is_bulk else rule['basis']
        
        line_total = count * unit_price
        total_parts_cost += line_total
        
        data_rows.append({
            "Bewerking (Code)": op,
            "Omschrijving": rule['naam'],
            "Aantal": count,
            "Tarief": "Bulk (>49)" if is_bulk else "Basis",
            "Stukprijs": f"€ {unit_price:.2f}",
            "Totaal": f"€ {line_total:.2f}"
        })

    # Starttarief logica
    # "Aanvangstarief t/m 49 stuks" -> Dit geldt meestal over het TOTAAL aantal bewerkingen of onderdelen.
    # Hier pas ik het toe als het totaal aantal bewerkingen <= 49 is.
    startup_cost = 0.0
    if total_count <= BULK_THRESHOLD:
        startup_cost = STARTUP_FEE

    final_total = total_parts_cost + startup_cost

    # --- WEERGAVE ---
    
    # 1. KPI's
    col1, col2, col3 = st.columns(3)
    col1.metric("Totaal Bewerkingen", total_count)
    col2.metric("Starttarief", f"€ {startup_cost:.2f}")
    col3.metric("Eindtotaal (excl. BTW)", f"€ {final_total:.2f}")
    
    st.divider()
    
    # 2. Detailtabel
    df = pd.DataFrame(data_rows)
    st.subheader("Specificatie")
    st.dataframe(df, use_container_width=True)
    
    # 3. Export
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download calculatie als CSV",
        data=csv,
        file_name="calculatie_2026.csv",
        mime="text/csv"
    )

    # Disclaimer voor gebruiker
    st.info(f"ℹ️ **Check de mapping:** Het systeem heeft '{', '.join(counts.keys())}' gevonden. Controleer of de prijzen kloppen bij deze tags.")

