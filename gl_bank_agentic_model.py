import streamlit as st
import pandas as pd
import re

# --- Categorization Functions ---

def normalize_text(s):
    if not isinstance(s, str):
        return ''
    s = s.upper()
    s = re.sub(r'\s+', ' ', s)  # compress whitespace
    return s.strip()

def categorize_gl(row):
    source = str(row.get('Source', '')).upper()
    desc   = str(row.get('Journal Line Description', '')).upper()
    if '117' in desc:
        return '117'
    elif '153' in desc:
        return '153'
    elif '119' in desc:
        return '119'
    elif 'NC BANK' in desc:
        return 'NC Bank'
    elif 'AP' in source:
        return 'AP'
    elif 'H11' in source:
        return 'TAX'
    else:
        return 'UNMATCHED'

def categorize_bank(row, col_text, col_type):
    raw_text = row.get(col_text, '')
    raw_type = row.get(col_type, '')
    T = normalize_text(raw_text)
    I = normalize_text(raw_type)
    
    # NC Bank
    nc_keywords = ["INDN:SETT-BATCH", "3351637714", "CO ID:3351637714", "CCD"]
    if all(k in T for k in nc_keywords):
        return "NC Bank"
    
    # 119
    keywords_119 = [
        "BNF:HERFF JONES LLC 4501 WEST 62ND STREET INDIANAPOLIS",
        "BNF BK:PNC BANK NATIONAL",
        "24295001305",
        "HERFF JONES LLC OPERATING ACCOUNT 4501",
        "JPMORGAN CHASE",
        "SND BK:WELLS FARGO BANK",
        "WELLS FARGO SWEEP",
        "24354001505",
        "JPMORGAN CHASE BANK"
    ]
    if any(k in T for k in keywords_119):
        return "119"
    
    if "TRSF" in T or "CUR" in T:
        return "117"
    
    if "BNF:LSC COMMUNICATIONS" in T:
        return "153"
    
    ap_words = ["CORP PMT", "VARSITY", "GOODS", "INV", "INTL OUT DATE:", "POP", "BALBOA", "VISION GEMS"]
    if (I == "DETAIL DEBITS" and any(w in T for w in ap_words)) or \
       (T.startswith("WIRE TYPE") and "INV" in T) or \
       ("ACH DETAIL RETURN CO ID:5351637714 CCD" in T and I == "DETAIL CREDITS"):
        return "AP"
    
    if ("TAX " in T or "TAXPAY" in T) and I == "DETAIL DEBITS":
        return "TAX"
    
    return "UNMATCHED"


# --- Streamlit UI and Logic ---

st.set_page_config(page_title='GL & Bank Agentic Model', layout='wide')
st.title('Agentic Model: GL & Bank Statement Categorization & Summary')

st.markdown("""
Upload your **GL Details CSV** and **Bank Statement Excel** files below (Bank header row assumed at row 6).
The app will categorize entries, provide summary aggregates, and let you explore by categories.
""")

uploaded_gl = st.file_uploader("Upload GL Details CSV", type=['csv'])
uploaded_bank = st.file_uploader("Upload Bank Statement Excel (xls/xlsx)", type=['xls', 'xlsx'])

gl_df = bank_df = None
summary_df = None

def find_col(columns, key):
    kl = key.replace(' ', '').lower()
    for c in columns:
        cl = str(c).replace(' ', '').lower()
        if kl in cl:
            return c
    return None

if uploaded_gl and uploaded_bank:
    # Load GL
    gl_df = pd.read_csv(uploaded_gl)
    gl_df['Remark'] = gl_df.apply(categorize_gl, axis=1)
    
    # Load Bank with header at line 6 (0-based index 5)
    bank_df = pd.read_excel(uploaded_bank, header=5)
    # Detect columns
    col_text = find_col(bank_df.columns, 'Text')
    col_type = find_col(bank_df.columns, 'Data Type')
    col_revsd_amt = find_col(bank_df.columns, 'Revsd amt')
    
    if not col_text or not col_type or not col_revsd_amt:
        st.error(f"Could not detect needed columns in Bank file. Columns found: {list(bank_df.columns)}")
        st.stop()
    
    bank_df['Remark'] = bank_df.apply(lambda r: categorize_bank(r, col_text, col_type), axis=1)
    
    # Aggregate summary
    gl_sum = gl_df.groupby('Remark')['Foreign Amount'].sum().rename('GL')
    bank_sum = bank_df.groupby('Remark')[col_revsd_amt].sum().rename('Bank Statement')
    
    summary_df = pd.concat([gl_sum, bank_sum], axis=1).fillna(0).reset_index().rename(columns={'Remark':'Category'})
    
    st.success("Files processed and remarks assigned.")
    
    # Show summary table
    st.header("Summary Table by Category")
    st.dataframe(summary_df.style.format({'GL': '{:,.2f}', 'Bank Statement': '{:,.2f}'}), use_container_width=True)
    
    csv = summary_df.to_csv(index=False).encode()
    st.download_button("Download Summary CSV", csv, file_name="summary_output.csv")
    
    # Detail view per category
    with st.expander("Explore details by Category"):
        selected_cat = st.selectbox("Select category", options=summary_df['Remark'] if 'Remark' in summary_df.columns else summary_df['Category'])
        
        st.subheader(f"GL Details for category: {selected_cat}")
        st.dataframe(gl_df[gl_df['Remark']==selected_cat], use_container_width=True)
        
        st.subheader(f"Bank Statement details for category: {selected_cat}")
        st.dataframe(bank_df[bank_df['Remark']==selected_cat], use_container_width=True)
    
    # Custom Query text input for remarks
    with st.expander("Query transactions by Remark"):
        user_query = st.text_input("Enter remark/category to filter (case insensitive), e.g., AP, TAX, 117, 119")
        if user_query:
            uq = user_query.strip().upper()
            
            gl_filtered = gl_df[gl_df['Remark'].str.upper() == uq]
            bank_filtered = bank_df[bank_df['Remark'].str.upper() == uq]
            
            st.write(f"### GL Details matching remark '{user_query}'")
            if len(gl_filtered):
                st.dataframe(gl_filtered, use_container_width=True)
            else:
                st.write("No matching GL records found.")
            
            st.write(f"### Bank Statement Details matching remark '{user_query}'")
            if len(bank_filtered):
                st.dataframe(bank_filtered, use_container_width=True)
            else:
                st.write("No matching Bank records found.")

else:
    st.info("Please upload both GL Details CSV and Bank Statement Excel files to proceed.")


st.markdown("""
---
*This app uses your custom categorization logic and file formats.  
Developed for easy inspection and analysis with flexible query capabilities.*
""")

