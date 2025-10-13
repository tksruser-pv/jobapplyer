import os
from openai import OpenAI
from typing import Dict, Tuple, Optional
# Import configparser here to make sure it's available within _load_config
import configparser 

# =================================================================
# CONFIGURATION LOADING (SIMPLIFIED & FIXED)
# =================================================================

def _load_config():
    """Reads configuration from config.ini using a simplified path check."""
    config = configparser.ConfigParser()
    
    # Explicitly check the main project config path first, then fallbacks
    possible_paths = [
        r"F:\tksr pv\jobapplyer\streamlit-job-app\config.ini",  # Explicit project config path
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.ini'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'config.ini'),
        os.path.join(os.getcwd(), 'config.ini'),
        os.path.join(os.getcwd(), 'config', 'config.ini'),
    ]
    config_path = None
    for path in possible_paths:
        if os.path.exists(path):
            config_path = path
            break

    default_api_key = ""
    default_model = "llama-3.1-8b-instant"
    default_prompt = "You are a professional assistant writing a brief, polite email."

    # Check if the file exists and attempt to read it
    if not config_path or not config.read(config_path):
        print("CRITICAL: config.ini not found. Using safe defaults for LLM operation.")
        return default_api_key, default_model, default_prompt

    try:
        groq_api_key = config['API_KEYS'].get('GROQ_API_KEY', default_api_key).strip()
        email_model = config['LLM_SETTINGS'].get('EMAIL_MODEL_NAME', default_model)
        email_system_prompt = config['LLM_SETTINGS'].get('EMAIL_SYSTEM_PROMPT', default_prompt)
        return groq_api_key, email_model, email_system_prompt
    except KeyError as e:
        print(f"ERROR: Missing required section or key in config.ini: {e}. Using defaults.")
        return default_api_key, default_model, default_prompt

# Load configuration and initialize client globally
GROQ_API_KEY, EMAIL_MODEL_NAME, EMAIL_SYSTEM_PROMPT = _load_config()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =================================================================
# EMAIL GENERATION FUNCTION (REST OF THE CODE REMAINS THE SAME)
# =================================================================

def generate_email(job_details: Dict[str, str], resume_path: str, recruiter_name: Optional[str], user_name: str, user_email: str) -> Tuple[str, str]:
    """
    Generates a tailored cover letter (email body) and subject line using the Groq LLM.

    Args:
        job_details: Dictionary containing job information (must include 'Company Name' and 'job description').
        resume_path: Path to the user's resume (kept for full signature compatibility, unused in prompt).
        recruiter_name: Name of the recruiter, if known.
        user_name: Applicant's name.
        user_email: Applicant's email.

    Returns:
        A tuple containing (email_body, subject_line).
    """
    # 1. Check for API key presence
    if not GROQ_API_KEY:
         print("[Groq Email Generator] API Key not configured. Using fallback template.")
         return _generate_fallback_email(job_details, recruiter_name, user_name)

    # 2. Extract Details
    company_name = job_details.get("Company Name", "the Company")
    # Using .get for safe access, assuming 'job description' might contain a space
    job_description = job_details.get("job description", "a specific role").strip() 
    job_title = job_details.get("Job Title", "Data Analyst/Engineer") 

    # 3. Construct the LLM Prompt
    
    # We use the system prompt loaded from config.ini
    system_instruction = (
        EMAIL_SYSTEM_PROMPT + 
        "\n\nGOAL: Tailor the content to show how the applicant's skills match the job requirements."
        "\nINSTRUCTIONS: 1. Start with a professional salutation. 2. Briefly reference 1-2 key skills (e.g., Python, SQL) from the JD. 3. Conclude with a strong call to action to review the attached resume. 4. Sign off professionally with the applicant's name."
    )

    user_prompt = f"""
    APPLICANT DETAILS: 
    - Name: {user_name}
    - Field: Business Analytics, Python, SQL, Algorithms, AI, Machine Learning.

    JOB DETAILS:
    - Company: {company_name}
    - Role: {job_title}
    - Recipient (if known): {recruiter_name or 'Hiring Team'}
    - Full Job Description: {job_description}
    """

    # 4. Call Groq API
    try:
        response = client.chat.completions.create(
            # Using the model name loaded from config.ini
            model=EMAIL_MODEL_NAME, 
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.4 
        )
        email_body = response.choices[0].message.content.strip()
        
        # 5. Define a Standard Subject
        subject = f"Application for {job_title} Position | {user_name}"
        
        return email_body, subject

    except Exception as e:
        print(f"[Groq Email Generator] Error during API call: {e}")
        return _generate_fallback_email(job_details, recruiter_name, user_name)

def _generate_fallback_email(job_details: Dict[str, str], recruiter_name: Optional[str], user_name: str) -> Tuple[str, str]:
    """Helper function to generate a basic email template if the API call fails."""
    company_name = job_details.get("Company Name", "the Company")
    job_title = job_details.get("Job Title", "Data Analyst/Engineer") 

    fallback_body = f"""
Dear {recruiter_name or 'Hiring Team'},

I am writing to express my strong interest in the {job_title} position at {company_name}. My qualifications align perfectly with the requirements outlined in the job description.

Please find my tailored resume attached for your review.

Sincerely,
{user_name}
"""
    subject = f"Application for {job_title} | {user_name}"
    return fallback_body.strip(), subject