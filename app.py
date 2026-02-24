import streamlit as st
import pandas as pd
import io

# --- PAGE SETUP ---
st.set_page_config(page_title="Survey Cruncher", layout="wide")
st.title("📊 Survey Data Cruncher (Version 4.4)")
st.write("Upload your raw survey data to generate clean tables.")

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
    
    with st.expander("Show Raw Data Preview (Check your columns here!)"):
        st.dataframe(df.head(10)) 

    # --- MAPPING COLUMNS ---
    st.divider()
    st.subheader("Step 1: Map Your Columns")
    
    all_columns = df.columns.tolist()
    
    id_col = st.selectbox("1. Select the Response ID column:", all_columns)
    demo_cols = st.multiselect("2. Select Demographic/Banner columns (e.g., Region, Gender):", all_columns)
    
    remaining_cols = [col for col in all_columns if col not in demo_cols and col != id_col]
    
    question_cols = st.multiselect("3. Select the Question columns you want to analyze:", remaining_cols)

    # --- CONFIGURATION ---
    st.divider()
    st.subheader("Step 2: Configuration")
    
    split_multicode = st.checkbox(
        "My data contains multi-select answers separated by commas (e.g., 'Apple, Banana')",
        value=False,
        help="Check this if your cells contain multiple answers that need to be counted separately."
    )

    st.subheader("Step 3: Generate Tables")
    
    # --- THE BUTTON & CRUNCHING ---
    if st.button("Crunch the Data! 🚀"):
        
        if not demo_cols or not question_cols:
            st.warning("⚠️ Please select at least one demographic and one question column above.")
        else:
            with st.spinner("Scrubbing data and calculating percentages..."):
                
                # 1. UNPIVOTING THE DATA
                long_data = pd.melt(
                    df,
                    id_vars=[id_col] + demo_cols,
                    value_vars=question_cols,
                    var_name='Question',
                    value_name='Answer'
                )
                
                # --- THE ROBUST SCRUBBER ---
                long_data = long_data.dropna(subset=['Answer'])
                long_data['Question'] = long_data['Question'].astype(str)
                long_data['Answer'] = long_data['Answer'].astype(str).str.strip()
                
                ghost_blanks = ['nan', 'None', '', '-', 'NaN', '<NA>']
                long_data = long_data[~long_data['Answer'].isin(ghost_blanks)]

                # --- MULTICODE SPLITTING ---
                if split_multicode:
                    long_data['Answer'] = long_data['Answer'].str.split(',')
                    long_data = long_data.explode('Answer')
                    long_data['Answer'] = long_data['Answer'].str.strip()
                    long_data = long_data[~long_data['Answer'].isin(ghost_blanks)]
                
                # --- PRESERVE ORIGINAL ORDER ---
                long_data['Question'] = pd.Categorical(
                    long_data['Question'], 
                    categories=question_cols, 
                    ordered=True
                )
                
                unique_answers = long_data['Answer'].unique().tolist()
                long_data['Answer'] = pd.Categorical(
                    long_data['Answer'], 
                    categories=unique_answers, 
                    ordered=True
                )

                tables_to_join = []
                
                # 2. OVERALL PERCENTAGES
                overall = pd.crosstab(index=[long_data['Question'], long_data['Answer']], columns='Overall %', dropna=True)
                overall_bases = long_data.groupby('Question', observed=True)[id_col].nunique()
                overall_pct = overall.div(overall_bases, level='Question', axis=0) * 100
                tables_to_join.append(overall_pct)
                
                # 3. DEMOGRAPHIC PERCENTAGES
                for col in demo_cols:
                    demo_tab = pd.crosstab(
                        index=[long_data['Question'], long_data['Answer']], 
                        columns=long_data[col],
                        dropna=True
                    )
                    
                    demo_bases = long_data.groupby(['Question', col], observed=True)[id_col].nunique().unstack(level=col)
                    demo_pct = demo_tab.div(demo_bases, level='Question', axis=0) * 100
                    demo_pct.columns = [f"{col}: {str(c)}" for c in demo_pct.columns]
                    tables_to_join.append(demo_pct)
                    
                # 4. GLUE THEM ALL TOGETHER
                final_report = pd.concat(tables_to_join, axis=1).fillna(0).round(1)
                
                # --- ADD TOP BASE SIZES (n) ROW ---
                base_sizes = {'Overall %': df[id_col].nunique()}
                
                for col in demo_cols:
                    counts = df.groupby(col)[id_col].nunique()
                    for cat, count in counts.items():
                        base_sizes[f"{col}: {str(cat)}"] = count
                        
                base_index = pd.MultiIndex.from_tuples([("BASE SIZE", "Total Survey Participants (n)")], names=['Question', 'Answer'])
                base_df = pd.DataFrame([base_sizes], index=base_index)
                
                final_report = pd.concat([base_df, final_report]).fillna(0)
                
                # --- FINAL CLEANUP ---
                final_report = final_report.reset_index()
                
                # Sort it using the strict Categories
                final_report['Question'] = pd.Categorical(final_report['Question'], categories=(['BASE SIZE'] + question_cols), ordered=True)
                final_report = final_report.sort_values(['Question'])
                
                # NEW FIX: Unlock the column back to normal text so it allows blank spaces!
                final_report['Question'] = final_report['Question'].astype(str)
                
                # Now we can safely blank out the duplicates
                final_report.loc[final_report['Question'].duplicated(), 'Question'] = ""
                
                st.success("✨ Analysis Complete!")
                st.write("### Your Final Banner Table (Percentages %)")
                st.dataframe(final_report)
                
                # 5. EXCEL DOWNLOAD
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    final_report.to_excel(writer, sheet_name='Survey Results', index=False)
                
                st.divider()
                st.download_button(
                    label="📥 Download Final Report to Excel",
                    data=excel_buffer.getvalue(),
                    file_name="Clean_Survey_Results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )