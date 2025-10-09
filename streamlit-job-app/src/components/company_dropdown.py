# calender code
from typing import List
import pandas as pd
import streamlit as st

def company_dropdown(excel_file: str) -> str:
    # Load the job details from the Excel file
    df = pd.read_excel(excel_file)

    # Extract unique company names
    company_names: List[str] = df['company name'].unique().tolist()

    # Create a dropdown for company selection
    selected_company = st.selectbox("Select a Company", company_names)

    return selected_company