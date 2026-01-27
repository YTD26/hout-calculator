import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# --- CONFIGURATIE: PRIJSLIJST 2026 (Q1) ---
# Hier mappen we de codes uit JOUW bestand (SawCut, HipRidgeCut) aan de prijslijst.

PRICING_MODEL = {
    # --- ZAAGWERK ---
    # SawCut kwam 214x voor in je bestand. Dit is de standaard zaagsnede.
    "SawCut":       {'naam': "Schuine kant per snede",   'basis': 0.90, 'bulk': 0.75},
    
    # HipRidgeCut kwam 7x voor. Dit zijn vaak complexere hoekkepersnedes.
    # Ik heb deze nu gemapt op 'Neigen' (duurder tarief), pas aan indien nodig.
    "HipRidgeCut":  {'naam': "Neigen per snede",         'basis': 1.50, 'bulk': 1.25},
    
    # --- BORINGEN (Nog niet gezien in je CSV, maar voor de zekerheid) ---
    "Drill":        {'naam': "Gaten boren (6-25mm)",     'basis': 0.95, 'bulk': 0.85},
    "DrillGroup":   {'naam': "Gaten + indoppen",         'basis': 2.70, 'bulk': 2.50},
    
    # --- KEPEN (Nog niet gezien, maar voor de zekerheid) ---
    "Slot":         {'naam': "Keep kopse kant (< 50mm)", 'basis': 1.90, 'bulk': 1.70},
    "LapJoin":      {'naam': "Keep midden (< 50mm)",     'basis': 3.75, 'bulk': 3.50},
    "Recess":       {'naam': "Keep midden (> 50mm)",     'basis': 4.25, 'bulk': 4.00}, 

    # --- FALLBACK ---
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

uploaded_file = st.file_uploader("Sleep je .bvx bestand hierheen", type=['bvx', 'xml', 'hmm'])

if uploaded_file is not None:
    content = uploaded_file.getvalue().decode("utf-8", errors='ignore')
    
    operations = []
    try:
        root = ET.fromstring(content)
        
        # UITGEBREIDE NEGEERLIJST
        # Deze tags zagen we in je CSV, maar zijn geen betaalde bewerkingen.
        ignore_list = [
            'BVX', 'Project', 'Header', 'Version', 'Timestamp', 'Cost', 'Description', 
            'Geometry', 'Name', 'Part', 'Parts', 'Job', 'Operations', 'AttDefs', 'Packages', 
            'Package', 'Container'
        ]
        
        for elem in root.iter():
            # Filter logic: 
            # 1. Mag niet in ignore lijst staan
            # 2. Tag moet langer zijn dan 2 letters
            if elem.tag not in ignore_list and len(elem.tag) > 2:
                operations.append(elem.tag)
                
    except ET.ParseError:
        st.error("⚠️ Dit bestand is geen geldige XML.")
        st.stop()

    if not operations:
        st.warning("Geen bewerkingen gevonden.")
        st.stop()

    counts = pd.Series(operations).value_counts().to_dict()
    
    data_rows = []
    total_parts_cost = 0.0
    total_count = sum(counts.values())

    for op, count in counts.items():
        # Zoek exacte match
        rule = PRICING_MODEL.get(op)
        
        # Geen exacte match? Zoek op deel van de naam
        if not rule:
            match_found = False
            for key, val in PRICING_MODEL.items():
                if key in op: # Bijv. "JackRafterCut" matcht met "Cut" als we dat willen
                    rule = val
                    match_found = True
                    break
            if not match_found:
                rule = PRICING_MODEL["Default"]

        # Staffelkorting
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

    # Starttarief
    startup_cost = 0.0
    if total_count <= BULK_THRESHOLD:
        startup_cost = STARTUP_FEE

    final_total = total_parts_cost + startup_cost

    # --- WEERGAVE ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Betaalde Bewerkingen", total_count)
    col2.metric("Starttarief", f"€ {startup_cost:.2f}")
    col3.metric("Eindtotaal (excl. BTW)", f"€ {final_total:.2f}")
    
    st.divider()
    
    df = pd.DataFrame(data_rows)
    # Sorteer zodat de duurste bovenaan staan
    df = df.sort_values(by="Totaal", ascending=False)
    
    st.subheader("Specificatie")
    st.dataframe(df, use_container_width=True)
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download calculatie als CSV", csv, "calculatie_2026.csv", "text/csv")


