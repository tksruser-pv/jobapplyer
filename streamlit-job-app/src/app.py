import streamlit as st
import pandas as pd
import os
from datetime import datetime
import configparser # New import for config loading

# Assuming these imports are correct based on your file structure
from components.calendar_dropdown import calendar_dropdown 
from utils.resume_editor import edit_resume 
from utils.email_generator import generate_email 
from utils.groq_scraper import get_recruiter_email 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# =================================================================
# CONFIGURATION LOADING
# =================================================================

def _load_main_config():
    """Reads the EXCEL_PATH from config.ini."""
    config = configparser.ConfigParser()
    config_paths = ['config.ini'] 
    
    # Define a default path if config is not found or key is missing
    default_path = r"F:\TKSR PRODUCTION\job1\a1.xlsx" 
    
    if not config.read(config_paths):
        print("WARNING: config.ini not found. Using default EXCEL_PATH.")
        return default_path

    try:
        # Load EXCEL_PATH from the [PATHS] section
        return config['PATHS'].get('EXCEL_PATH', default_path)
    except KeyError:
        print("WARNING: [PATHS] section or EXCEL_PATH key missing in config.ini. Using default EXCEL_PATH.")
        return default_path

# Load the Excel path from the configuration file
EXCEL_PATH = _load_main_config()

# =================================================================
# UTILITY FUNCTIONS
# =================================================================

def send_email(to_email, subject, body, from_email, from_password, attachment_path=None):
    """Handles SMTP connection and sends the email with attachment."""
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    try:
        server.login(from_email, from_password)
    except smtplib.SMTPAuthenticationError:
        raise Exception("Authentication failed! Use a Gmail App Password, not your regular password.")
    server.send_message(msg)
    server.quit()


def find_recruiter_email(job_details, hr_name="", company_name=""):
    """
    Priority check for recruiter email, using the standardized column name 'recruiter_email'.

    1. Direct column lookup from the current job_details row.
    2. Fallback to Groq/Scraping logic (get_recruiter_email).
    """
    # 1. Direct recruiter email lookup (using the standardized key 'recruiter_email')
    email = job_details.get("recruiter_email")
    
    # Check if the value is not NaN and contains '@'
    if pd.notna(email) and "@" in str(email):
        return str(email).strip()
            
    # 2. Fallback: use Groq scraper logic
    # Note: hr_name and company_name are already passed in, and we look for 
    # the standardized 'job_description' key in the row data.
    job_description = job_details.get("job_description", "")
    return get_recruiter_email(hr_name, company_name, job_description)

# =================================================================
# MAIN STREAMLIT APPLICATION
# =================================================================

def main():
    st.title("📩 Job Application Portal")

    # User Inputs
    # Note: calendar_dropdown is assumed to return a datetime.date object
    selected_date = calendar_dropdown() 
    user_resume = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])
    user_name = st.text_input("Your Name")
    user_email = st.text_input("Your Gmail Address")
    from_password = st.text_input("Enter your Gmail App Password", type="password")

    # Load and clean job details
    try:
        if not os.path.exists(EXCEL_PATH):
            st.error(f"Excel file not found at configured path: {EXCEL_PATH}")
            return

        job_details_df = pd.read_excel(EXCEL_PATH)
        
        # 1. CRITICAL CLEANUP STEP: Standardize all column names (lowercase + underscores)
        job_details_df.columns = job_details_df.columns.str.strip().str.lower().str.replace(" ", "_")

        # --- DATE HANDLING (Robust and Correct) ---
        # 1. Convert the 'date' column to datetime
        job_details_df['date_dt'] = pd.to_datetime(
            job_details_df.get("date"), # Use .get to handle missing 'date' column safely
            errors="coerce", 
            dayfirst=True 
        )
        
        # 2. Convert to a standardized string format for reliable comparison (YYYY-MM-DD)
        job_details_df['date_str'] = job_details_df['date_dt'].dt.strftime('%Y-%m-%d')
        
        # 3. Standardize the Streamlit selected date to the same string format.
        if hasattr(selected_date, "strftime"):
            selected_date_str = selected_date.strftime('%Y-%m-%d')
        else:
            # Fallback if dropdown returns an unexpected object type
            st.error("Invalid date object received from calendar dropdown.")
            return
        
        # Filter jobs for selected date using the standardized string column
        jobs_for_date = job_details_df[job_details_df["date_str"] == selected_date_str].copy()
        
    except Exception as e:
        st.error(f"Failed to read job details Excel or process data: {e}")
        return
    
    st.subheader("📊 Job Data for Selected Date")
    # Display relevant columns
    display_cols = ['company_name', 'recruiter_name', 'recruiter_email', 'job_description']
    # Filter columns to only show those that exist
    st.dataframe(jobs_for_date[[col for col in display_cols if col in jobs_for_date.columns]].head()) 

    # Submit Application
    if st.button("Submit Application"):
        # ... (Input Validations remain the same) ...
        if not selected_date or user_resume is None or not user_name or not user_email or not from_password:
            st.error("Please fill in all required fields and upload your resume before submitting.")
            return
        if jobs_for_date.empty:
            st.warning(f"No companies available for the selected date ({selected_date_str}). Please choose another date.")
            return

        # Save uploaded resume
        os.makedirs("temp_resume", exist_ok=True)
        # Use a unique temporary name for the uploaded file
        resume_save_path = os.path.join(
            "temp_resume", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_resume.name}"
        )
        with open(resume_save_path, "wb") as f:
            f.write(user_resume.getbuffer())

        success_count = 0
        fail_count = 0
        debug_results = []

        # Start processing jobs
        for _, job_details_row in jobs_for_date.iterrows():
            
            # --- EXTRACTING DATA USING STANDARDIZED KEYS ---
            job_description = job_details_row.get("job_description", "")
            company_name = job_details_row.get("company_name", "UnknownCompany") 
            recruiter_name = job_details_row.get("recruiter_name", "") 
            
            if not job_description:
                 st.warning(f"Skipping {company_name}: Job description is missing.")
                 fail_count += 1
                 continue

            # 1. Create job-specific edited resume (Output is Markdown, as per tool update)
            # The output path should be .md since the LLM editor tool outputs markdown
            output_path = os.path.join("temp_resume", f"edited_resume_{company_name}.md")
            
            # The edit_resume function now returns the path string directly
            try:
                edited_resume_path = edit_resume(resume_save_path, job_description, output_path)
            except Exception as e:
                st.error(f"LLM Resume Edit Failed for {company_name}: {e}")
                fail_count += 1
                continue
                
            # 2. Find Recruiter Email (Uses Direct lookup then Groq Scraper)
            recruiter_email = find_recruiter_email(job_details_row, recruiter_name, company_name)
            
            if not recruiter_email or str(recruiter_email).lower() in ["none", "nan", ""]:
                st.error(f"No valid recruiter email found for {company_name}, skipping email attempt...")
                fail_count += 1
                debug_results.append({
                    "Company": company_name,
                    "Recruiter": recruiter_name,
                    "Resolved Email": "❌ Not Found"
                })
                continue
            
            # Fix common typo
            recruiter_email = recruiter_email.replace("@gamil.com", "@gmail.com") 

            debug_results.append({
                "Company": company_name,
                "Recruiter": recruiter_name,
                "Resolved Email": recruiter_email
            })

            # --- SEND EMAIL BLOCK ---
            try:
                # Generate email body and subject (returns a tuple: body, subject)
                # Note: job_details_row (Pandas Series) is passed here
                email_content, subject = generate_email(
                    job_details_row.to_dict(), edited_resume_path, recruiter_name, user_name, user_email
                )

                # Send email
                send_email(
                    recruiter_email,
                    subject,
                    email_content,
                    user_email,
                    from_password,
                    edited_resume_path, # Attachment: the new markdown resume
                )
                st.success(f"✅ Successfully sent application to {company_name} at {recruiter_email}")
                success_count += 1
                
            except Exception as e:
                st.error(f"❌ Failed to send email to {recruiter_email} ({company_name}): {e}")
                fail_count += 1

        # Show debug table
        st.subheader("📊 Recruiter Email Resolution")
        st.dataframe(pd.DataFrame(debug_results))

        # Final summary
        if success_count > 0:
            st.success(f"✅ Applications sent to {success_count} companies for {selected_date_str}!")
        if fail_count > 0:
            st.warning(f"⚠️ Failed to send applications to {fail_count} companies.")

if __name__ == "__main__":
    main()
