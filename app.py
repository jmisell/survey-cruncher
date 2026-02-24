import streamlit as st
import pandas as pd
import io
import statsmodels.api as sm

# --- PAGE SETUP ---
st.set_page_config(page_title="Survey Cruncher", layout="wide")
st.title("📊 Survey Data Cruncher (Version 5.0)")
st.write("Upload your raw survey data to generate clean tables and run advanced analytics.")

# --- FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload Raw Survey Data (Excel or CSV)", type=["xlsx", "csv"])

if uploaded_file is not None:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
        
    st.success("File uploaded successfully!")
    
    st.write(f"**Total Respondents:** {df.shape[0]}")
    st.write(f"**Total Columns:** {df.shape[1]}")
    
    # --- MAPPING COLUMNS ---
    st.divider()
    st.subheader("Step 1: Map Your Columns")
    
    all_columns = df.columns.tolist()
    id_col = st.selectbox("1. Select the Response ID column:", all_columns)
    demo_cols = st.multiselect("2. Select Demographic/Banner columns (e.g., Region, Gender):", all_columns)
    
    remaining_cols = [col for col in all_columns if col not in demo_cols and col != id_col]
    question_cols = st.multiselect("3. Select the Question columns you want to analyze:", remaining_cols)

    st.divider()
    
    # --- TABS SETUP ---
    tab1, tab2 = st.tabs(["📊 1. Cross-Tabs & Percentages", "🎯 2. Key Driver Analysis (Regression)"])

    # ==========================================
    # TAB 1: CROSS-TABS (Your existing app)
    # ==========================================
    with tab1:
        st.subheader("Configuration")
        split_multicode = st.checkbox(
            "My data contains multi-select answers separated by commas (e.g., 'Apple, Banana')",
            value=False,
            help="Check this if your cells contain multiple answers that need to be counted separately."
        )

        if st.button("Crunch the Data! 🚀"):
            if not demo_cols or not question_cols:
                st.warning("⚠️ Please select at least one demographic and one question column above.")
            else:
                with st.spinner("Scrubbing data and calculating percentages..."):
                    long_data = pd.melt(df, id_vars=[id_col] + demo_cols, value_vars=question_cols, var_name='Question', value_name='Answer')
                    
                    long_data = long_data.dropna(subset=['Answer'])
                    long_data['Question'] = long_data['Question'].astype(str)
                    long_data['Answer'] = long_data['Answer'].astype(str).str.strip()
                    
                    ghost_blanks = ['nan', 'None', '', '-', 'NaN', '<NA>']
                    long_data = long_data[~long_data['Answer'].isin(ghost_blanks)]

                    if split_multicode:
                        long_data['Answer'] = long_data['Answer'].str.split(',')
                        long_data = long_data.explode('Answer')
                        long_data['Answer'] = long_data['Answer'].str.strip()
                        long_data = long_data[~long_data['Answer'].isin(ghost_blanks)]
                    
                    long_data['Question'] = pd.Categorical(long_data['Question'], categories=question_cols, ordered=True)
                    unique_answers = long_data['Answer'].unique().tolist()
                    long_data['Answer'] = pd.Categorical(long_data['Answer'], categories=unique_answers, ordered=True)

                    tables_to_join = []
                    
                    overall = pd.crosstab(index=[long_data['Question'], long_data['Answer']], columns='Overall %', dropna=True)
                    overall_bases = long_data.groupby('Question', observed=True)[id_col].nunique()
                    overall_pct = overall.div(overall_bases, level='Question', axis=0) * 100
                    tables_to_join.append(overall_pct)
                    
                    for col in demo_cols:
                        demo_tab = pd.crosstab(index=[long_data['Question'], long_data['Answer']], columns=long_data[col], dropna=True)
                        demo_bases = long_data.groupby(['Question', col], observed=True)[id_col].nunique().unstack(level=col)
                        demo_pct = demo_tab.div(demo_bases, level='Question', axis=0) * 100
                        demo_pct.columns = [f"{col}: {str(c)}" for c in demo_pct.columns]
                        tables_to_join.append(demo_pct)
                        
                    final_report = pd.concat(tables_to_join, axis=1).fillna(0).round(1)
                    
                    base_sizes = {'Overall %': df[id_col].nunique()}
                    for col in demo_cols:
                        counts = df.groupby(col)[id_col].nunique()
                        for cat, count in counts.items():
                            base_sizes[f"{col}: {str(cat)}"] = count
                            
                    base_index = pd.MultiIndex.from_tuples([("BASE SIZE", "Total Survey Participants (n)")], names=['Question', 'Answer'])
                    base_df = pd.DataFrame([base_sizes], index=base_index)
                    
                    final_report = pd.concat([base_df, final_report]).fillna(0).reset_index()
                    
                    final_report['Question'] = pd.Categorical(final_report['Question'], categories=(['BASE SIZE'] + question_cols), ordered=True)
                    final_report = final_report.sort_values(['Question'])
                    final_report['Question'] = final_report['Question'].astype(str)
                    final_report.loc[final_report['Question'].duplicated(), 'Question'] = ""
                    
                    st.success("✨ Cross-Tabs Complete!")
                    st.dataframe(final_report)
                    
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        final_report.to_excel(writer, sheet_name='Survey Results', index=False)
                    
                    st.download_button("📥 Download Cross-Tabs to Excel", data=excel_buffer.getvalue(), file_name="Clean_Survey_Results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


    # ==========================================
    # TAB 2: KEY DRIVER ANALYSIS (REGRESSION)
    # ==========================================
    with tab2:
        st.write("### Multiple Regression Analysis")
        st.write("Find out which questions are the strongest statistical drivers of your target outcome.")
        
        target_col = st.selectbox("🎯 1. Select your Target Variable (The outcome you want to predict):", question_cols)
        driver_cols = st.multiselect("🧠 2. Select your Driver Variables (The questions you think influence the target):", [c for c in question_cols if c != target_col])
        
        if st.button("Run Key Driver Analysis 📈"):
            if not target_col or not driver_cols:
                st.warning("⚠️ Please select one Target and at least one Driver.")
            else:
                with st.spinner("Converting text to numbers and calculating regression..."):
                    
                    # 1. Isolate the data
                    reg_data = df[[target_col] + driver_cols].copy()
                    
                    # 2. Text-to-Number Scoring Dictionary
                    scale_mapping = {
                        "Strongly agree": 5, "Agree": 4, "Neutral": 3, "Disagree": 2, "Strongly disagree": 1,
                        "Strongly Agree": 5, "Strongly Disagree": 1 # Catching capitalization differences
                    }
                    
                    # Apply the mapping to turn text into numbers
                    for col in reg_data.columns:
                        reg_data[col] = reg_data[col].map(lambda x: scale_mapping.get(str(x).strip(), pd.NA))
                        
                    # 3. Drop missing data (Regression requires full rows)
                    clean_reg_data = reg_data.dropna()
                    
                    st.write(f"*Running model on {len(clean_reg_data)} valid respondents who answered all selected questions.*")
                    
                    if len(clean_reg_data) < 15:
                        st.error("🚨 Not enough valid numerical data to run a regression. Ensure your selected questions use a 5-point agree/disagree scale.")
                    else:
                        # 4. Run the Math
                        Y = clean_reg_data[target_col].astype(float)
                        X = clean_reg_data[driver_cols].astype(float)
                        X = sm.add_constant(X) # Required for OLS regression
                        
                        model = sm.OLS(Y, X).fit()
                        
                        # 5. Format the Results
                        results_df = pd.DataFrame({
                            "Driver Question": model.params.index,
                            "Impact Score (Coefficient)": model.params.values.round(3),
                            "P-Value": model.pvalues.values.round(4)
                        })
                        
                        # Remove the 'const' baseline row
                        results_df = results_df[results_df["Driver Question"] != "const"]
                        
                        # Calculate Statistical Significance
                        results_df["Significant?"] = results_df["P-Value"].apply(lambda x: "✅ Yes" if x < 0.05 else "❌ No")
                        
                        # Sort by biggest impact
                        results_df = results_df.sort_values("Impact Score (Coefficient)", ascending=False).reset_index(drop=True)
                        
                        st.success("✨ Regression Complete!")
                        st.dataframe(results_df, use_container_width=True)
                        
                        st.info("""
                        **How to read this table:**
                        * **Impact Score:** How much your Target score increases for every 1-point increase in the Driver question. (Higher is better).
                        * **Significant?:** If 'Yes' (p-value < 0.05), we are 95% confident this relationship is real and not just a random fluke.
                        """)