import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# --- CONFIGURATIE ---
# Pas dit aan naar jouw echte prijzen
PRIJSLIJST = {
    "Saw": 1.50,
    "Drill": 0.75,
    "Slot": 2.50,
    "Mark": 0.20,
    "Mill": 3.00,
    "Inkjet": 0.10,
    "Default": 0.00
    "Operations": 100.00
}

st.set_page_config(page_title="Hout Calculator", page_icon="🌲")

st.title("🌲 Houtbewerking Calculator")
st.markdown("Upload een **.bvx** bestand om bewerkingen te tellen.")

# File Uploader
uploaded_file = st.file_uploader("Sleep je bestand hierheen", type=['bvx', 'xml', 'hmm'])

if uploaded_file is not None:
    # 1. Bestand lezen
    # We lezen het als bytes en decoderen, 'ignore' voorkomt crashes bij vreemde tekens
    content = uploaded_file.getvalue().decode("utf-8", errors='ignore')
    
    # 2. XML Parsen
    operations = []
    try:
        # Ervan uitgaande dat BVX XML-structuur heeft
        root = ET.fromstring(content)
        
        # We itereren door alle tags. 
        # Voor BVX bestanden zijn tags vaak de operatienamen (zoals <Saw>, <Drill>)
        ignore_list = ['BVX', 'Project', 'Header', 'Version', 'Timestamp', 'Cost', 'Description']
        
        for elem in root.iter():
            # Filtert de technische tags eruit
            if elem.tag not in ignore_list and len(elem.tag) > 2:
                operations.append(elem.tag)
                
    except ET.ParseError:
        st.error("⚠️ Dit bestand lijkt geen geldige XML structuur te hebben.")
        st.stop()

    if not operations:
        st.warning("Geen herkenbare bewerkingen gevonden.")
        st.stop()

    # 3. Berekeningen
    counts = pd.Series(operations).value_counts().to_dict()
    
    data_rows = []
    total_price = 0.0

    for op, count in counts.items():
        # Prijs match logica (zoekt 'Saw' in 'SawCuts' etc.)
        unit_price = PRIJSLIJST.get("Default")
        match_type = "Overig"
        
        for key, price in PRIJSLIJST.items():
            if key.lower() in op.lower():
                unit_price = price
                match_type = key
                break
        
        line_total = count * unit_price
        total_price += line_total
        
        data_rows.append({
            "Bewerking": op,
            "Categorie": match_type,
            "Aantal": count,
            "Stukprijs": f"€ {unit_price:.2f}",
            "Totaal": f"€ {line_total:.2f}"
        })

    # 4. Resultaten Tonen
    df = pd.DataFrame(data_rows)
    
    # Metrics bovenin
    col1, col2, col3 = st.columns(3)
    col1.metric("Aantal Bewerkingen", sum(counts.values()))
    col2.metric("Unieke Types", len(counts))
    col3.metric("Totaalprijs", f"€ {total_price:.2f}")
    
    st.divider()
    st.dataframe(df, use_container_width=True)
    
    # Download optie voor administratie
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download overzicht als CSV", csv, "calculatie.csv", "text/csv")
