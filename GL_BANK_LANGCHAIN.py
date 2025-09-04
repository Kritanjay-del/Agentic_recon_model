import streamlit as st
import pandas as pd
import re
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

# -- Categorization logic from your script --
def normalize_text(s):
    if not isinstance(s, str):
        return ''
    s = s.upper()
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def categorize_gl(row):
    source = str(row.get('Source', '')).upper()
    desc = str(row.get('Journal Line Description', '')).upper()
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
    elif 'H11' in source or 'TAX' in source:
        return 'TAX'
    else:
        return 'UNMATCHED'

def categorize_bank(row, col_text, col_type):
    raw_text = row.get(col_text, '')
    raw_type = row.get(col_type, '')
    T = normalize_text(raw_text)
    I = normalize_text(raw_type)

    nc_keywords = ["INDN:SETT-BATCH", "3351637714", "CO ID:3351637714", "CCD"]
    if all(k in T for k in nc_keywords):
        return "NC Bank"

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

def find_col(columns, key):
    kl = key.replace(' ', '').lower()
    for c in columns:
        cl = str(c).replace(' ', '').lower()
        if kl in cl:
            return c
    return None

# --- Streamlit + LangChain App ---

st.title("GL & Bank Smart AI Analyst (LangChain-powered)")

st.markdown("Upload GL and Bank statement. After preprocessing, you can ask natural language questions about your data (e.g., 'What's the total for category 117?' or 'Show all unmatched entries in Bank').")

gl_file = st.file_uploader("GL Details CSV", type=["csv"])
bank_file = st.file_uploader("Bank Statement Excel (header row 6)", type=["xls", "xlsx"])

if gl_file and bank_file:
    gl_df = pd.read_csv(gl_file)
    gl_df["Remark"] = gl_df.apply(categorize_gl, axis=1)

    bank_df = pd.read_excel(bank_file, header=5)
    col_text = find_col(bank_df.columns, "Text")
    col_type = find_col(bank_df.columns, "Data Type")
    col_revsd_amt = find_col(bank_df.columns, "Revsd amt")
    if not col_text or not col_type or not col_revsd_amt:
        st.error(f"Bank file missing required columns! Found: {list(bank_df.columns)}")
        st.stop()
    bank_df["Remark"] = bank_df.apply(lambda r: categorize_bank(r, col_text, col_type), axis=1)

    # Summaries for reference
    gl_sum = gl_df.groupby('Remark')["Foreign Amount"].sum().rename("GL")
    bank_sum = bank_df.groupby('Remark')[col_revsd_amt].sum().rename("Bank Statement")
    summary_df = pd.concat([gl_sum, bank_sum], axis=1).fillna(0).reset_index().rename(columns={"Remark":"Category"})

    st.subheader("Category-wise Summary")
    st.dataframe(summary_df, use_container_width=True)

    csv_bytes = summary_df.to_csv(index=False).encode()
    st.download_button("Download Summary CSV", data=csv_bytes, file_name="summary_output.csv")

    st.divider()
    st.header("💬 Ask the AI Anything About Your Statements")

    # ---- Setup LangChain agent ----
    # You must set your OpenAI API key
    import os
    openai_key = st.secrets.get("OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
    if not openai_key:
        openai_key = st.text_input("Enter your OpenAI API Key (not stored):", type="password")
    if openai_key:
        # Minimal demo: Use both DataFrames as agent tools
        # You can merge/rename columns if needed, or pass as 2 separate frames.
        agent = create_pandas_dataframe_agent(
            ChatOpenAI(model="gpt-4o", temperature=0, openai_api_key=openai_key),
            [gl_df, bank_df],
            verbose=False,
            allow_dangerous_code=True
        )

        user_query = st.text_area("Type your question (examples: 'Show all AP transactions', 'Total for NC Bank')", height=60)
        if st.button("Ask AI") and user_query.strip():
            with st.spinner("AI is thinking..."):
                try:
                    result = agent.run(user_query)
                    st.write(result)
                except Exception as e:
                    st.error(f"AI Error: {e}")

        st.markdown("""
        **Tips:**  
        - Try: `What's the total by Remark for GL?`  
        - `Show all TAX records in Bank statement.`  
        - `Sum of Foreign Amount for unmatched in GL.`  
        - `Which category has the highest amount in Bank?`  
        """)
    else:
        st.info("Enter your OpenAI API key above to enable the AI agent.")

else:
    st.info("Please upload both GL and Bank files.")

st.caption("LangChain + Streamlit agentic app: Ask anything about your processed GL and Bank tables!")


