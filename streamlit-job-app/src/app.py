import streamlit as st
import pandas as pd
import os
from datetime import datetime
# Assuming these imports are correct based on your file structure
from components.calendar_dropdown import calendar_dropdown 
from utils.resume_editor import edit_resume 
from utils.email_generator import generate_email 
from utils.groq_scraper import get_recruiter_email 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

EXCEL_PATH = r"F:\TKSR PRODUCTION\job1\a1.xlsx"


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


# app.py (Replace existing find_recruiter_email function)

def find_recruiter_email(job_details, hr_name="", company_name=""):
    """
    Priority check for recruiter email:
    1. Direct column lookup from the current job_details row (CRITICAL FIX)
    2. Fallback to Groq/Scraping logic
    """
    # 1. Direct recruiter email lookup
    # Check for the known column names: 'recruiter email' (lowercase, space) 
    # and 'Recruiter Email' (if present from other sources)
    for col in ["recruiter email", "Recruiter Email"]: 
        email = job_details.get(col)
        # Check if the value is not NaN and contains '@'
        if pd.notna(email) and "@" in str(email):
             return str(email).strip()
            
    # NOTE: The job_details row only contains the email if it was in the Excel file.
    # If not found, fall back to the advanced search.
    
    # 2. Fallback: use Groq scraper logic
    job_description = job_details.get("job description", "")
    return get_recruiter_email(hr_name, company_name, job_description)

# Ensure the main loop in app.py uses the exact column names:
# company_name = job_details.get("Company Name", "UnknownCompany") 
# recruiter_name = job_details.get("recruiter name", "")


def main():
    st.title("📩 Job Application Portal")

    # User Inputs
    selected_date = calendar_dropdown()
    user_resume = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])
    user_name = st.text_input("Your Name")
    user_email = st.text_input("Your Gmail Address")
    from_password = st.text_input("Enter your Gmail App Password", type="password")

    # Load and clean job details
    try:
        job_details_df = pd.read_excel(EXCEL_PATH)
        
        # 1. CRITICAL CLEANUP STEP: Standardize all column names (lowercase + underscores)
        job_details_df.columns = job_details_df.columns.str.strip().str.lower().str.replace(" ", "_")

        # --- DATE HANDLING (Robust and Correct) ---
        # 1. Convert the 'date' column to datetime, explicitly setting dayfirst=True 
        job_details_df['date_dt'] = pd.to_datetime(
            job_details_df["date"], 
            errors="coerce", 
            dayfirst=True 
        )
        
        # 2. Convert to a standardized string format for reliable comparison (YYYY-MM-DD)
        job_details_df['date_str'] = job_details_df['date_dt'].dt.strftime('%Y-%m-%d')
        
        # 3. Standardize the Streamlit selected date to the same string format.
        if hasattr(selected_date, "strftime"):
             selected_date_str = selected_date.strftime('%Y-%m-%d')
        else:
             st.error("Invalid date object received from calendar dropdown.")
             return
        
        # Filter jobs for selected date using the standardized string column
        jobs_for_date = job_details_df[job_details_df["date_str"] == selected_date_str].copy()
        
    except Exception as e:
        st.error(f"Failed to read job details Excel or process dates: {e}")
        return
    
    st.subheader("📊 Job Data for Selected Date")
    # Display jobs_for_date after filtering
    st.dataframe(jobs_for_date[['company_name', 'recruiter_name', 'recruiter_email', 'job_description']].head()) 

    st.write("Current DataFrame columns (lowercase_underscore):", job_details_df.columns.tolist())

    # Submit Application
    if st.button("Submit Application"):
        # Validate inputs
        if not selected_date:
            st.error("Please select a date before submitting.")
            return
        if user_resume is None:
            st.error("Please upload your resume before submitting.")
            return
        if not user_name or not user_email:
            st.error("Please enter your name and email.")
            return
        if not from_password:
            st.error("Please enter your Gmail App Password.")
            return
        if jobs_for_date.empty:
            st.warning(f"No companies available for the selected date ({selected_date_str}). Please choose another date.")
            return

        # Save uploaded resume
        os.makedirs("temp_resume", exist_ok=True)
        resume_save_path = os.path.join(
            "temp_resume", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_resume.name}"
        )
        with open(resume_save_path, "wb") as f:
            f.write(user_resume.getbuffer())

        success_count = 0
        fail_count = 0
        debug_results = []

        for _, job_details in jobs_for_date.iterrows():
            # --- CRITICAL FIX: USE CLEANED COLUMN NAMES ---
            # Use 'company_name', 'recruiter_name', 'job_description'
            job_description = job_details.get("job_description", "")
            company_name = job_details.get("company_name", "UnknownCompany") 
            recruiter_name = job_details.get("recruiter_name", "") 
            # ---------------------------------------------

            print(f"DEBUG: Processing Company: {company_name}") # Check the extracted name

            # Create job-specific edited resume
            output_path = f"edited_resume_{company_name}_{datetime.now().strftime('%H%M%S')}.pdf"
            edited_resume_result = edit_resume(resume_save_path, job_description, output_path)
            edited_resume_path = edited_resume_result[0] if isinstance(edited_resume_result, tuple) else edited_resume_result

            # Note: find_recruiter_email must be updated in app.py to only look for
            # 'recruiter_email' since the column names were standardized.
            recruiter_email = find_recruiter_email(job_details, recruiter_name, company_name)
            
            # --- Robust check for 'nan' and empty string before sending ---
            if not recruiter_email or str(recruiter_email).lower() in ["none", "nan", ""]:
                st.error(f"No valid recruiter email found for {company_name}, skipping...")
                fail_count += 1
                continue
            
            # Fix common typo (optional, but good)
            recruiter_email = recruiter_email.replace("@gamil.com", "@gmail.com") 

            debug_results.append({
                "Company": company_name,
                "Recruiter": recruiter_name,
                "Resolved Email": recruiter_email or "❌ Not Found"
            })

            # --- START ROBUST EMAIL BLOCK ---
            try:
                # Generate email body and subject (returns a tuple: body, subject)
                email_content, subject = generate_email(
                    job_details, edited_resume_path, recruiter_name, user_name, user_email
                )

                # Send email
                send_email(
                    recruiter_email,
                    subject,
                    email_content,
                    user_email,
                    from_password,
                    edited_resume_path, # This is the 6th argument (attachment_path)
                )
                st.success(f"✅ Successfully sent application to {company_name} at {recruiter_email}")
                success_count += 1
                
            except Exception as e:
                # Catch failures in email generation or sending
                st.error(f"❌ Failed to send email to {recruiter_email}: {e}")
                fail_count += 1
            # --- END ROBUST EMAIL BLOCK ---

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