import streamlit as st
import pandas as pd
import io

# --- PAGE SETUP ---
st.set_page_config(page_title="Survey Cruncher", layout="wide")
st.title("📊 Survey Data Cruncher")
st.write("Upload your raw survey data to generate clean tables.")

# --- FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload Raw Survey Data (Excel or CSV)", type=["xlsx", "csv"])

if uploaded_file is not None:
    # Read the file depending on its type
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
        
    st.success("File uploaded successfully!")
    
    st.write(f"**Total Respondents:** {df.shape[0]}")
    st.write(f"**Total Columns:** {df.shape[1]}")
    
    with st.expander("Show Raw Data Preview"):
        st.dataframe(df.head(10)) 

    # --- MAPPING COLUMNS ---
    st.divider()
    st.subheader("Step 1: Map Your Columns")
    
    all_columns = df.columns.tolist()
    
    id_col = st.selectbox("1. Select the Response ID column:", all_columns)
    
    demo_cols = st.multiselect(
        "2. Select Demographic/Banner columns (e.g., Region, Gender):", 
        all_columns
    )
    
    remaining_cols = [col for col in all_columns if col not in demo_cols and col != id_col]
    
    question_cols = st.multiselect(
        "3. Select the Question columns you want to analyze:", 
        remaining_cols
    )

    # --- NEW OPTION: MULTICODE SPLITTER ---
    st.divider()
    st.subheader("Step 2: Configuration")
    
    # The new checkbox for handling comma-separated answers
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
            with st.spinner("Unpivoting and calculating percentages... (this takes milliseconds!)"):
                
                # 1. UNPIVOTING THE DATA
                long_data = pd.melt(
                    df,
                    id_vars=[id_col] + demo_cols,
                    value_vars=question_cols,
                    var_name='Question',
                    value_name='Answer'
                )
                
                # Clean up: remove blank answers
                long_data = long_data.dropna(subset=['Answer'])
                
                # Force everything to string to prevent crashes
                long_data['Question'] = long_data['Question'].astype(str)
                long_data['Answer'] = long_data['Answer'].astype(str)

                # --- NEW LOGIC: HANDLE MULTICODE SPLITTING ---
                if split_multicode:
                    # 1. Split by comma (creates a list: ['Apple', ' Banana'])
                    long_data['Answer'] = long_data['Answer'].str.split(',')
                    # 2. Explode the list into separate rows
                    long_data = long_data.explode('Answer')
                    # 3. Trim whitespace (removes the space before ' Banana')
                    long_data['Answer'] = long_data['Answer'].str.strip()
                # ---------------------------------------------
                
                # 2. BUILDING THE BANNER TABLES
                tables_to_join = []
                
                # Create the 'Overall %' column
                overall = pd.crosstab(index=[long_data['Question'], long_data['Answer']], columns='Overall %')
                
                # IMPORTANT: Calculate percentage based on UNIQUE respondents (Base Size), not row count
                # This ensures multi-code percentages are correct (can sum > 100%)
                total_respondents = df[id_col].nunique()
                overall_pct = (overall / total_respondents) * 100
                
                tables_to_join.append(overall_pct)
                
                # Create a column for every demographic selected
                for col in demo_cols:
                    prefixed_demo = col + ": " + df[col].astype(str)
                    
                    # We need to join the demographic info back to the exploded data to get the right counts
                    # But since long_data already has the demo cols, we can just use them!
                    
                    # Calculate counts for this subgroup
                    # We use the demographic column from long_data which is aligned with the answers
                    demo_tab = pd.crosstab(
                        index=[long_data['Question'], long_data['Answer']], 
                        columns=long_data[col]
                    )
                    
                    # Calculate base sizes for this specific demographic group from the ORIGINAL dataframe
                    # This ensures the denominator is "Total People in Group", not "Total Answers Given"
                    demo_bases = df.groupby(col)[id_col].nunique()
                    
                    # Divide counts by the correct base size
                    demo_pct = demo_tab.div(demo_bases, axis=1) * 100
                    
                    # Rename columns to include the prefix (e.g., "Gender: Male")
                    demo_pct.columns = [f"{col}: {c}" for c in demo_pct.columns]
                    
                    tables_to_join.append(demo_pct)
                    
                # 3. GLUE THEM ALL TOGETHER
                final_report = pd.concat(tables_to_join, axis=1).fillna(0).round(1)
                
                # --- ADD BASE SIZES (n) ROW ---
                base_sizes = {'Overall %': df[id_col].nunique()}
                
                for col in demo_cols:
                    counts = df.groupby(col)[id_col].nunique()
                    for cat, count in counts.items():
                        base_sizes[f"{col}: {str(cat)}"] = count
                        
                base_index = pd.MultiIndex.from_tuples([("BASE SIZE", "Base (n)")], names=['Question', 'Answer'])
                base_df = pd.DataFrame([base_sizes], index=base_index)
                
                final_report = pd.concat([base_df, final_report]).fillna(0)
                
                # --- FINAL CLEANUP ---
                final_report = final_report.reset_index()
                final_report.loc[final_report['Question'].duplicated(), 'Question'] = ""
                
                st.success("✨ Analysis Complete!")
                st.write("### Your Final Banner Table (Percentages %)")
                st.dataframe(final_report)
                
                # 4. EXCEL DOWNLOAD
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
                