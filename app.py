import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import pytesseract
import json
import re
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_bytes
from openai import OpenAI

# ==========================================
# CONFIGURATIE
# ==========================================

STANDAARD_RUW_MATEN = [
    (38.0, 89.0), (38.0, 120.0), (38.0, 140.0), (38.0, 170.0),
    (38.0, 235.0), (45.0, 70.0), (50.0, 100.0), (75.0, 200.0)
]

SCHAAF_CODES = ["G10-1", "G10-5", "GESCHAAFD"]

# Standaard prijzen - kunnen aangepast worden via sidebar
DEFAULT_PRIJZEN = {
    "SawCut_Recht": 0.50,
    "SawCut_Schuin": 0.90,
    "HipRidgeCut": 1.50,
    "Drill": 0.95,
    "Slot": 1.90,
    "Lap": 3.75,
    "BirdsMouth": 2.50,
    "Neig": 1.80,
    "Toeslag_Schaven_m1": 1.25,
    "Stelkosten_Schaven": 50.00,
    "Stelkosten_Korten": 25.00
}

IGNORED_OPERATIONS = ['TextOutput', 'BvnMacro']

# ==========================================
# PRIJZEN CONNECTOR FUNCTIES
# ==========================================

def load_prices_from_external_source():
    """
    Placeholder functie voor externe prijzen connector.
    Kan later uitgebreid worden met:
    - API call naar prijzendatabase
    - Lezen van externe configuratie file
    - Database connectie
    - Per-klant prijzen uit CRM systeem
    """
    # TODO: Implementeer externe prijzen connector hier
    # Bijvoorbeeld:
    # - API: requests.get("https://api.example.com/prijzen")
    # - Database: cursor.execute("SELECT * FROM prijzen WHERE klant_id = ?")
    # - File: json.load(open("klant_prijzen.json"))
    
    return None  # Geeft None als er geen externe prijzen zijn

def get_active_prices():
    """
    Haalt actieve prijzen op uit session state of gebruikt defaults.
    """
    if 'custom_prijzen' not in st.session_state:
        # Probeer eerst externe prijzen te laden
        external_prices = load_prices_from_external_source()
        st.session_state.custom_prijzen = external_prices if external_prices else DEFAULT_PRIJZEN.copy()
    
    return st.session_state.custom_prijzen

# ==========================================
# HULPFUNCTIES
# ==========================================

def extract_text_from_image(image_input):
    try:
        image = image_input if isinstance(image_input, Image.Image) else Image.open(image_input)
        return pytesseract.image_to_string(image, lang='eng')
    except Exception as e:
        return f"OCR fout: {e}"

def clean_data_with_perplexity(raw_text):
    client = OpenAI(
        api_key=st.secrets["PERPLEXITY_API_KEY"], 
        base_url="https://api.perplexity.ai"
    )
    
    prompt = f"""Extract houtbestellingsgegevens uit deze OCR tekst en retourneer alleen valide JSON.
    
Formaat:
[{{"Aantal": 5, "Omschrijving": "Vuren", "Dikte": 38, "Breedte": 140, "Lengte": 3000, "Toeslagen": "Schaven"}}]

Tekst:
{raw_text[:3000]}"""

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI fout: {e}"

def parse_json_response(response_text):
    try:
        start = response_text.find('[')
        end = response_text.rfind(']') + 1
        return pd.read_json(response_text[start:end])
    except Exception:
        return None

def extract_project_name(content, root):
    job_node = root.find(".//Job")
    project_naam = job_node.get("Project", "") if job_node else ""
    
    if not project_naam:
        match = re.search(r'<!--\s*project:?\s*([A-Za-z0-9-]+)', content, re.IGNORECASE)
        project_naam = match.group(1) if match else "Onbekend"
    
    return project_naam

def vereist_schaven(width, height, tekst):
    for code in SCHAAF_CODES:
        if code in tekst.upper():
            return True, f"Code {code}"
    
    for dim in STANDAARD_RUW_MATEN:
        if (abs(width - dim[0]) < 1.0 and abs(height - dim[1]) < 1.0) or \
           (abs(width - dim[1]) < 1.0 and abs(height - dim[0]) < 1.0):
            return False, ""
    
    return True, "Afwijkende Maat"

def parse_operations(operations_container):
    """Tel bewerkingen per type voor nauwkeurige prijsberekening."""
    if operations_container is None:
        return [], {}
    
    ops_list = []
    ops_count = {}
    
    for op in operations_container:
        if op.tag in IGNORED_OPERATIONS:
            continue
        
        if op.tag == 'SawCut':
            angle = float(op.get('Angle', 90))
            bevel = float(op.get('Bevel', 90))
            code = "SawCut_Recht" if abs(angle - 90.0) < 0.1 and abs(bevel - 90.0) < 0.1 else "SawCut_Schuin"
        else:
            code = op.tag
        
        ops_list.append(code)
        ops_count[code] = ops_count.get(code, 0) + 1
    
    return ops_list, ops_count

def format_operations(ops_count):
    """Maak leesbare string zoals 'SawCut_Recht (2x), Lap (1x)'."""
    if not ops_count:
        return "-"
    return ", ".join([f"{op} ({count}x)" for op, count in ops_count.items()])

def parse_bvx_data(root, content):
    project_naam = extract_project_name(content, root)
    parts_data = []
    
    for part in root.findall('.//Part'):
        qty = int(part.get('ReqQuantity', 1))
        width = float(part.get('Width', 0))
        height = float(part.get('Height', 0))
        length = float(part.get('Length', 0))
        
        full_text = f"{part.get('Name', '')} {part.get('Grade', '')} {part.get('Comments', '')}"
        
        operations, ops_count = parse_operations(part.find('Operations'))
        moet_schaven, schaafreden = vereist_schaven(width, height, full_text)
        
        # Elke bewerking krijgt eigen kolom
        sawcut_recht = ops_count.get('SawCut_Recht', 0)
        sawcut_schuin = ops_count.get('SawCut_Schuin', 0)
        lap = ops_count.get('Lap', 0)
        birdsmouth = ops_count.get('BirdsMouth', 0)
        neig = ops_count.get('Neig', 0)
        hipridgecut = ops_count.get('HipRidgeCut', 0)
        drill = ops_count.get('Drill', 0)
        slot = ops_count.get('Slot', 0)
        
        # Totaal: ALLEEN Schuin, Lap, BirdsMouth, Neig (NIET SawCut_Recht, NIET HipRidgeCut)
        totaal_bewerkingen = sawcut_schuin + lap + birdsmouth + neig
        
        # NIEUW: Totaal bewerkingen × aantal balken
        totaal_bewerkingen_stuks = totaal_bewerkingen * qty
        
        parts_data.append({
            "Positie": part.get('Name', ''),
            "Aantal": qty,
            "Dikte": width,
            "Breedte": height,
            "Lengte (mm)": round(length, 0),
            "Kwaliteit": part.get('Grade', ''),
            "SawCut_Recht": sawcut_recht,
            "SawCut_Schuin": sawcut_schuin,
            "Lap": lap,
            "BirdsMouth": birdsmouth,
            "Neig": neig,
            "HipRidgeCut": hipridgecut,
            "Drill": drill,
            "Slot": slot,
            "Totaal": totaal_bewerkingen,
            "Totaal Bewerkingen (stuks)": totaal_bewerkingen_stuks,  # NIEUWE KOLOM
            "Toeslagen": schaafreden if schaafreden else "-",
            "Raw_Ops": operations,
            "Ops_Count": ops_count,
            "Moet_Schaven": moet_schaven,
            "Meters": (length / 1000.0) * qty
        })
    
    return pd.DataFrame(parts_data), project_naam

def bereken_prijzen(df, prijzen):
    """Berekent prijzen op basis van daadwerkelijk aantal bewerkingen."""
    total_price = 0.0
    heeft_schaafwerk = df['Moet_Schaven'].any()
    
    for _, row in df.iterrows():
        line_cost = 0.0
        qty = row['Aantal']
        
        for op, count in row['Ops_Count'].items():
            line_cost += prijzen.get(op, 0.0) * count * qty
        
        if row['Moet_Schaven']:
            line_cost += row['Meters'] * prijzen['Toeslag_Schaven_m1']
        
        total_price += line_cost
    
    stelkosten = prijzen['Stelkosten_Korten']
    if heeft_schaafwerk:
        stelkosten += prijzen['Stelkosten_Schaven']
    
    return total_price + stelkosten, stelkosten, heeft_schaafwerk

def create_excel_download(df, project_naam):
    """Maakt een Excel bestand met proper formatting."""
    output = BytesIO()
    
    # Selecteer kolommen voor export
    export_df = df[['Positie', 'Aantal', 'Dikte', 'Breedte', 'Lengte (mm)', 
                    'Kwaliteit', 'SawCut_Recht', 'SawCut_Schuin', 'Lap', 'BirdsMouth', 
                    'Neig', 'HipRidgeCut', 'Drill', 'Slot', 'Totaal', 
                    'Totaal Bewerkingen (stuks)', 'Toeslagen']].copy()
    
    # Schrijf naar Excel met pandas ExcelWriter
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Calculatie')
        
        # Haal worksheet op voor formatting
        worksheet = writer.sheets['Calculatie']
        
        # Auto-width voor kolommen
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    return output

def process_pdf(uploaded_file):
    images = convert_from_bytes(uploaded_file.getvalue())
    full_text = ""
    progress_bar = st.progress(0)
    
    for i, image in enumerate(images):
        st.image(image, caption=f"Pagina {i+1}", width=700)
        full_text += f"\n--- PAGINA {i+1} ---\n{extract_text_from_image(image)}"
        progress_bar.progress((i + 1) / len(images))
    
    return full_text

def process_ocr_result(raw_text):
    if len(raw_text) < 10:
        st.warning("Geen tekst gevonden.")
        return
    
    with st.expander("Bekijk ruwe tekst"):
        st.text(raw_text)
    
    st.info("🧠 Perplexity analyseert...")
    json_response = clean_data_with_perplexity(raw_text)
    
    df = parse_json_response(json_response)
    
    if df is not None:
        st.subheader("Gevonden Specificaties")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, "scan_resultaat.csv", "text/csv")
    else:
        st.error("Kon data niet verwerken. AI Output:")
        st.write(json_response)

# ==========================================
# STYLING
# ==========================================

st.set_page_config(page_title="Heuvelman Hout Calculator", page_icon="🪵", layout="wide")

st.markdown("""
<style>
.header-container {
    background-color: #003366;
    padding: 20px;
    border-bottom: 5px solid #FFCC00;
    margin-bottom: 30px;
    border-radius: 5px;
    color: white;
}
.logo-main {
    font-size: 32px;
    font-weight: 800;
    color: #FFCC00;
    font-family: 'Arial Black', sans-serif;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.logo-sub {
    color: white;
    font-size: 18px;
    font-weight: 400;
    margin-left: 10px;
}
h1, h2, h3 {
    color: #003366 !important;
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-weight: 700;
}
div.stButton > button {
    background-color: #FFCC00;
    color: #003366;
    border-radius: 0px;
    border: none;
    padding: 10px 24px;
    font-weight: bold;
    text-transform: uppercase;
}
div.stButton > button:hover {
    background-color: #E6B800;
}
thead tr th {
    background-color: #003366 !important;
    color: white !important;
}
[data-testid="stFileUploader"] {
    border: 2px dashed #003366;
    background-color: #F4F8FB;
}
[data-testid="stMetricValue"] {
    color: #003366;
}
hr {
    border-top: 2px solid #FFCC00;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# SIDEBAR - PRIJZEN CONFIGURATIE
# ==========================================

with st.sidebar:
    st.header("⚙️ Instellingen")
    st.subheader("Prijzen Configuratie")
    
    # Informatie over prijzen
    st.info("💡 **Tip:** Prijzen kunnen per klant verschillen. Pas hier de actieve prijzen aan.")
    
    # Toggle voor geavanceerde prijzen editor
    show_price_editor = st.checkbox("Prijzen aanpassen", value=False)
    
    if show_price_editor:
        st.markdown("---")
        prijzen = get_active_prices()
        
        st.markdown("**Bewerkingen**")
        prijzen['SawCut_Recht'] = st.number_input("SawCut Recht (€)", value=prijzen['SawCut_Recht'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['SawCut_Schuin'] = st.number_input("SawCut Schuin (€)", value=prijzen['SawCut_Schuin'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['HipRidgeCut'] = st.number_input("HipRidgeCut (€)", value=prijzen['HipRidgeCut'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['Drill'] = st.number_input("Drill (€)", value=prijzen['Drill'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['Slot'] = st.number_input("Slot (€)", value=prijzen['Slot'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['Lap'] = st.number_input("Lap (€)", value=prijzen['Lap'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['BirdsMouth'] = st.number_input("BirdsMouth (€)", value=prijzen['BirdsMouth'], min_value=0.0, step=0.05, format="%.2f")
        prijzen['Neig'] = st.number_input("Neig (€)", value=prijzen['Neig'], min_value=0.0, step=0.05, format="%.2f")
        
        st.markdown("---")
        st.markdown("**Toeslagen**")
        prijzen['Toeslag_Schaven_m1'] = st.number_input("Toeslag Schaven per meter (€)", value=prijzen['Toeslag_Schaven_m1'], min_value=0.0, step=0.05, format="%.2f")
        
        st.markdown("---")
        st.markdown("**Stelkosten**")
        prijzen['Stelkosten_Schaven'] = st.number_input("Stelkosten Schaven (€)", value=prijzen['Stelkosten_Schaven'], min_value=0.0, step=5.0, format="%.2f")
        prijzen['Stelkosten_Korten'] = st.number_input("Stelkosten Korten (€)", value=prijzen['Stelkosten_Korten'], min_value=0.0, step=5.0, format="%.2f")
        
        # Reset knop
        if st.button("↻ Reset naar standaard prijzen"):
            st.session_state.custom_prijzen = DEFAULT_PRIJZEN.copy()
            st.rerun()
        
        st.success("✅ Aangepaste prijzen actief")
    else:
        st.markdown("🔒 Standaard prijzen actief")
    
    st.markdown("---")
    st.markdown("**Toekomstige features:**")
    st.markdown("• API connectie voor prijzen")
    st.markdown("• Per-klant prijzen database")
    st.markdown("• Import/Export prijzen")

# ==========================================
# HOOFDAPPLICATIE
# ==========================================

st.markdown("""
<div class="header-container">
    <div style="display: flex; align-items: center;">
        <div style="background-color: #FFCC00; width: 50px; height: 50px; display: flex; 
                    align-items: center; justify-content: center; margin-right: 15px; 
                    font-size: 30px; font-weight: bold; color: #003366;">H</div>
        <div>
            <span class="logo-main">HEUVELMAN</span><br>
            <span class="logo-sub">maakt hout mooier</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.title("Calculatie Tool")
st.markdown("**We leveren niet zomaar hout: We leveren oplossingen.**  \n"
            "Upload uw BVX-bestand, afbeelding of PDF voor een directe calculatie.")

uploaded_file = st.file_uploader("Sleep bestand hierheen", type=['bvx', 'xml', 'jpg', 'png', 'jpeg', 'pdf'])

if uploaded_file:
    file_type = uploaded_file.name.split('.')[-1].lower()
    
    # Haal actieve prijzen op
    actieve_prijzen = get_active_prices()
    
    if file_type in ['bvx', 'xml']:
        content = uploaded_file.getvalue().decode("utf-8", errors='ignore')
        
        try:
            root = ET.fromstring(content)
            df, project_naam = parse_bvx_data(root, content)
            total_price, stelkosten, heeft_schaafwerk = bereken_prijzen(df, actieve_prijzen)
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Project", project_naam)
            c2.metric("Totaal Balken", df['Aantal'].sum())
            c3.metric("Stelkosten", f"€ {stelkosten:.2f}")
            c4.metric("Totaalprijs (excl. BTW)", f"€ {total_price:.2f}")
            
            st.divider()
            st.subheader("📋 Materiaalspecificatie & Bewerkingen")
            
            view_df = df[['Positie', 'Aantal', 'Dikte', 'Breedte', 'Lengte (mm)', 
                          'Kwaliteit', 'SawCut_Recht', 'SawCut_Schuin', 'Lap', 'BirdsMouth', 
                          'Neig', 'HipRidgeCut', 'Drill', 'Slot', 'Totaal', 
                          'Totaal Bewerkingen (stuks)', 'Toeslagen']].copy()
            
            st.dataframe(
                view_df.style.apply(
                    lambda x: ['background-color: #fff4e5' if any(t in str(x['Toeslagen']) 
                               for t in ['Code', 'Afwijkend']) else '' for _ in x], 
                    axis=1
                ), 
                use_container_width=True
            )
            
            if heeft_schaafwerk:
                st.warning(f"⚠️ Let op: {df['Moet_Schaven'].sum()} regels vereisen schaven "
                          f"(stelkosten €{actieve_prijzen['Stelkosten_Schaven']:.2f} toegevoegd).")
            
            # Excel download knop
            excel_data = create_excel_download(df, project_naam)
            st.download_button(
                label="📥 Download Calculatie (Excel)",
                data=excel_data,
                file_name=f"calculatie_{project_naam}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        except Exception as e:
            st.error(f"Fout bij verwerken bestand: {e}")
    
    elif file_type == 'pdf':
        st.info("📄 PDF wordt verwerkt...")
        try:
            full_text = process_pdf(uploaded_file)
            st.success("Alle pagina's gescand!")
            process_ocr_result(full_text)
        except Exception as e:
            st.error(f"PDF fout: {e}")
    
    elif file_type in ['jpg', 'png', 'jpeg']:
        st.info("📸 Afbeelding wordt gescand...")
        raw_text = extract_text_from_image(uploaded_file)
        process_ocr_result(raw_text)
