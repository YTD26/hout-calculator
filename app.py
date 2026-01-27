import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# ==========================================
# 1. CONFIGURATIE (Pas dit aan voor jouw situatie)
# ==========================================

# VRAAG 2: Standaard 'Ruwe' Maten (Geen schaaftoeslag)
# Als een balk NIET deze maat heeft, gaan we ervan uit dat hij geschaafd moet worden.
# Format: (Dikte, Breedte) in mm. Let op puntjes ipv komma's!
STANDAARD_RUW_MATEN = [
    (38.0, 89.0),   # SLS
    (38.0, 120.0),
    (38.0, 140.0),  # Vuren C18/C24
    (38.0, 170.0),
    (38.0, 235.0),
    (45.0, 70.0),   # Balkhout
    (50.0, 100.0),
    (75.0, 200.0)
]

# Codes die ALTIJD schaaftarief triggeren (Vraag 2: G10-1, G10-5)
# We zoeken deze tekst in de Naam, Grade of Comments van de balk.
SCHAAF_CODES = ["G10-1", "G10-5", "GESCHAAFD"]

# Prijslijst configuratie
PRIJZEN = {
    # Materiaalbewerkingen (per stuk)
    "SawCut_Recht":  0.50, # Afkorten (Rechte zaagsnede)
    "SawCut_Schuin": 0.90, # Schuin zagen (Angle != 90)
    "HipRidgeCut":   1.50, # Hoekkeper / Nok
    "Drill":         0.95, # Boren
    "Slot":          1.90, # Kepen
    "Lap":           3.75, # Halfhoutsverbinding
    
    # Toeslagen (Vraag 2)
    "Toeslag_Schaven_m1": 1.25,  # Prijs per meter voor schaven? (Of per stuk?)
    "Stelkosten_Schaven": 50.00, # Eenmalige startkosten als er geschaafd moet worden
    "Stelkosten_Korten":  25.00  # Eenmalige startkosten zaagwerk
}

# ==========================================
# 2. DE APPLICATIE
# ==========================================

import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# ---------------------------------------------------------
# STYLING CONFIGURATIE (HEUVELMAN HOUT STIJL)
# ---------------------------------------------------------
st.set_page_config(
    page_title="Heuvelman Hout Calculator", 
    page_icon="🌲", 
    layout="wide"
)

# Custom CSS injecteren voor de exacte Heuvelman look
st.markdown("""
    <style>
    /* Hoofdtitels in Heuvelman Rood */
    h1, h2, h3 {
        color: #D94539 !important;
        font-family: 'Montserrat', sans-serif;
        font-weight: 700;
    }
    
    /* Metrics (KPI's) styling */
    [data-testid="stMetricValue"] {
        color: #D94539;
        font-weight: bold;
    }
    
    /* Upload Box styling */
    [data-testid="stFileUploader"] {
        border: 2px dashed #D94539;
        background-color: #FEF6F5;
        padding: 20px;
        border-radius: 10px;
    }
    
    /* Tabellen headers rood maken */
    thead tr th:first-child {display:none}
    thead tr th {
        background-color: #D94539 !important;
        color: white !important;
    }

    /* Knoppen styling */
    div.stButton > button {
        background-color: #D94539;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
    }
    div.stButton > button:hover {
        background-color: #B0342A; /* Iets donkerder bij hover */
        color: white;
    }
    
    /* Download button specifiek */
    div.stDownloadButton > button {
        background-color: #333333;
        color: white;
    }
    
    /* Logo container (optioneel, als je een logo URL hebt) */
    .logo-container {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }
    .logo-text {
        font-size: 24px;
        font-weight: bold;
        color: #333333;
        margin-left: 10px;
    }
    .red-dot { color: #D94539; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# HEADER MET LOGO (Tekstueel nagemaakt)
# ---------------------------------------------------------
st.markdown("""
    <div class="logo-container">
        <!-- Je zou hier ook een echte <img> tag kunnen gebruiken als je de URL hebt -->
        <span class="logo-text">HEUVELMAN<span class="red-dot">HOUT</span></span>
    </div>
    <hr style="border-top: 3px solid #D94539; margin-top: 0;">
""", unsafe_allow_html=True)

st.title("Calculatie Tool")
st.markdown("**Wij leveren oplossingen.** Upload uw BVX-bestand voor een directe calculatie.")

# ... HIERONDER KOMT DE REST VAN JE BESTAANDE CODE (Vanaf uploaded_file = ...)


uploaded_file = st.file_uploader("Sleep je bestand hierheen", type=['bvx', 'xml'])

if uploaded_file:
    # Bestand inlezen
    content = uploaded_file.getvalue().decode("utf-8", errors='ignore')
    
    try:
        root = ET.fromstring(content)
        
        parts_data = []
        project_naam = root.find(".//Job").get("Project", "Onbekend") if root.find(".//Job") is not None else "Onbekend"
        
        # Loop door alle onderdelen (Parts)
        for part in root.findall('.//Part'):
            # 1. Eigenschappen ophalen (Specificatie Vraag 1)
            p_name = part.get('Name', '')
            p_width = float(part.get('Width', 0))
            p_height = float(part.get('Height', 0))
            p_length = float(part.get('Length', 0))
            p_qty = int(part.get('ReqQuantity', 1)) # Aantal stuks
            p_grade = part.get('Grade', '') 
            p_comments = part.get('Comments', '')
            
            # Combineer tekstvelden om te zoeken naar G10 codes
            full_text_search = f"{p_name} {p_grade} {p_comments}".upper()
            
            # 2. Bewerkingen analyseren
            ops_in_part = []
            operations_container = part.find('Operations')
            
            if operations_container is not None:
                for op in operations_container:
                    tag = op.tag
                    
                    # Slimme detectie: Recht vs Schuin zagen
                    if tag == 'SawCut':
                        angle = float(op.get('Angle', 90))
                        bevel = float(op.get('Bevel', 90))
                        # Marge van 0.1 graad voor afronding
                        if abs(angle - 90.0) < 0.1 and abs(bevel - 90.0) < 0.1:
                            code = "SawCut_Recht"
                        else:
                            code = "SawCut_Schuin"
                    elif tag in ['TextOutput', 'BvnMacro']:
                        continue # Negeren
                    else:
                        code = tag # Overige (Drill, HipRidge, Lap, etc)
                    
                    ops_in_part.append(code)

            # 3. LOGICA VRAAG 2: Schaven & Toeslagen
            toeslagen = []
            moet_schaven = False
            
            # Check A: Zit er een G10 code in?
            for code in SCHAAF_CODES:
                if code in full_text_search:
                    moet_schaven = True
                    toeslagen.append(f"Code {code}")
                    break
            
            # Check B: Wijkt de maat af van standaard?
            # We checken of (width, height) OF (height, width) in de lijst staat (hout kan gedraaid zijn)
            is_standaard = False
            for dim in STANDAARD_RUW_MATEN:
                if (abs(p_width - dim[0]) < 1.0 and abs(p_height - dim[1]) < 1.0) or \
                   (abs(p_width - dim[1]) < 1.0 and abs(p_height - dim[0]) < 1.0):
                    is_standaard = True
                    break
            
            if not is_standaard and not moet_schaven:
                moet_schaven = True
                toeslagen.append("Afwijkende Maat")

            # Data opslaan
            parts_data.append({
                "Positie": p_name,
                "Aantal": p_qty,
                "Dikte": p_width,
                "Breedte": p_height,
                "Lengte (mm)": round(p_length, 0),
                "Kwaliteit": p_grade,
                "Bewerkingen": ", ".join(set(ops_in_part)),
                "Toeslagen": ", ".join(toeslagen) if toeslagen else "-",
                "Raw_Ops": ops_in_part,
                "Moet_Schaven": moet_schaven,
                "Meters": (p_length / 1000.0) * p_qty # Voor prijscalculatie
            })

        # DataFrame maken
        df = pd.DataFrame(parts_data)
        
        # ==========================================
        # 3. PRIJS BEREKENING
        # ==========================================
        total_price = 0.0
        details_log = []
        
        # Variabelen voor stelkosten
        heeft_schaafwerk = df['Moet_Schaven'].any()
        heeft_zaagwerk = True # Nagenoeg altijd waar bij BVX
        
        # A. Regelkosten (Materiaal + Bewerking)
        for idx, row in df.iterrows():
            line_cost = 0.0
            qty = row['Aantal']
            
            # 1. Bewerkingskosten
            for op in row['Raw_Ops']:
                line_cost += PRIJZEN.get(op, 0.0) * qty
            
            # 2. Schaafkosten (Per meter of per stuk? Hier per m1 gedaan)
            if row['Moet_Schaven']:
                line_cost += row['Meters'] * PRIJZEN['Toeslag_Schaven_m1']
            
            total_price += line_cost
            
        # B. Stelkosten (Eenmalig per project)
        stelkosten = 0.0
        if heeft_zaagwerk:
            stelkosten += PRIJZEN['Stelkosten_Korten']
        if heeft_schaafwerk:
            stelkosten += PRIJZEN['Stelkosten_Schaven']
            
        total_price += stelkosten

        # ==========================================
        # 4. DASHBOARD WEERGAVE
        # ==========================================
        
        # KPI's
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Project", project_naam)
        c2.metric("Totaal Balken", df['Aantal'].sum())
        c3.metric("Stelkosten", f"€ {stelkosten:.2f}")
        c4.metric("Totaalprijs (excl. BTW)", f"€ {total_price:.2f}")
        
        st.divider()
        
        # VRAAG 1: Specificatie Lijst
        st.subheader("📋 Materiaalspecificatie & Bewerkingen")
        
        # We maken een mooie tabel voor de klant
        view_df = df[['Positie', 'Aantal', 'Dikte', 'Breedte', 'Lengte (mm)', 'Kwaliteit', 'Toeslagen', 'Bewerkingen']].copy()
        
        # Highlight regels met schaafwerk
        st.dataframe(view_df.style.apply(lambda x: ['background-color: #fff4e5' if 'Code' in str(x['Toeslagen']) or 'Afwijkend' in str(x['Toeslagen']) else '' for i in x], axis=1), use_container_width=True)
        
        # VRAAG 2: Nettomaten controle
        if heeft_schaafwerk:
            st.warning(f"⚠️ Let op: Er zijn {df['Moet_Schaven'].sum()} regels die geschaafd moeten worden (G10 code of afwijkende maat). Stelkosten à €{PRIJZEN['Stelkosten_Schaven']} zijn toegevoegd.")
        
        # Export knop
        csv = view_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Calculatie (CSV)", csv, f"calculatie_{project_naam}.csv", "text/csv")

    except Exception as e:
        st.error(f"Er ging iets mis bij het lezen van het bestand: {e}")

