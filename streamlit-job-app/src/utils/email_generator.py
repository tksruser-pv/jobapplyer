import os
from openai import OpenAI
from typing import Dict, Tuple, Optional
import configparser 
import logging

# Setup basic logging to differentiate config messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('GroqConfig')

# =================================================================
# CONFIGURATION LOADING 
# =================================================================

def _load_config():
    """
    Reads configuration from config.ini, prioritizing environment variables.
    
    If no valid key is found, it defaults to an empty string, which ensures 
    the API call is skipped later, forcing the safe fallback mode.
    """
    config = configparser.ConfigParser()
    config_read = False
    
    # Define paths to check for config.ini (current directory and parent directory)
    possible_paths = [
        os.path.join(os.getcwd(), 'config.ini'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.ini'), 
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            config.read(path)
            config_read = True
            logger.info(f"Successfully read config from: {path}")
            break
    
    if not config_read:
        logger.warning("No config.ini file found in checked paths. Relying only on Environment Variables.")

    groq_api_key = "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"
    
    # Priority 1: Environment Variable (Best Practice)
    # --- FIX 1: Removed hardcoded key assignment here ---
    if os.environ.get('GROQ_API_KEY'):
        groq_api_key = os.environ.get('GROQ_API_KEY').strip()
        logger.info("Key found via environment variable (Priority 1).")
    
    # Priority 2: config.ini file
    if not groq_api_key and config_read:
        try:
            # Use .get with a default of None
            key_from_config = config['API_KEYS'].get('GROQ_API_KEY')
            if key_from_config:
                groq_api_key = key_from_config.strip()
                logger.info("Key found via config.ini file (Priority 2).")
        except KeyError:
            logger.warning("Config file read, but [API_KEYS] section or GROQ_API_KEY missing.")
            pass # Continue if section is missing

    # Priority 3: Final Fallback Check
    if not groq_api_key:
        print("CRITICAL: Groq API Key not found in environment or config. LLM will use fallback template.")
        # --- FIX 2: Removed hardcoded key assignment here ---
        # Final safeguard: ensure it's an empty string if not found.
        groq_api_key = "" 

    # Fallback settings for model and prompt
    default_model = "llama-3.1-8b-instant"
    default_prompt = "You are a professional assistant writing a brief, polite email."
    
    try:
        email_model = config['LLM_SETTINGS'].get('EMAIL_MODEL_NAME', default_model)
        email_system_prompt = config['LLM_SETTINGS'].get('EMAIL_SYSTEM_PROMPT', default_prompt)
    except KeyError:
        # Use default settings if LLM_SETTINGS section is missing
        email_model = default_model
        email_system_prompt = default_prompt

    return groq_api_key, email_model, email_system_prompt

# Load configuration and initialize client globally
GROQ_API_KEY, EMAIL_MODEL_NAME, EMAIL_SYSTEM_PROMPT = _load_config()

# Initialize the OpenAI client wrapper with the key (if available)
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =================================================================
# EMAIL GENERATION FUNCTION (MODIFIED TO ADD SIGNATURE)
# =================================================================

def generate_email(
    job_details: Dict[str, str], 
    resume_path: str, 
    recruiter_name: Optional[str], 
    user_name: str, 
    user_email: str,
    user_phone: Optional[str] = None,
    user_linkedin: Optional[str] = None
) -> Tuple[str, str]:
    """
    Generates a tailored cover letter (email body) and subject line using the Groq LLM.

    The final output is formatted with a custom signature.

    Args:
        job_details: Dictionary containing job information.
        resume_path: Path to the user's resume (unused in prompt, kept for function compatibility).
        recruiter_name: Name of the recruiter, if known.
        user_name: Applicant's name.
        user_email: Applicant's email.
        user_phone: Applicant's phone number.
        user_linkedin: Applicant's LinkedIn profile URL.

    Returns:
        A tuple containing (full_email_body_with_signature, subject_line).
    """
    
    # 1. Check for API key presence (GROQ_API_KEY will be "" if not found)
    # The length check is the most reliable way to enforce the skip
    if not GROQ_API_KEY or len(GROQ_API_KEY.strip()) < 5:
        # Note: This message is separate from the CRITICAL print in _load_config
        print("[Groq Email Generator] API Key not configured or is too short. Using fallback template.")
        return _generate_fallback_email(job_details, recruiter_name, user_name, user_phone, user_linkedin)

    # 2. Extract Details (Standardize keys from excel data)
    company_name = job_details.get("company_name", "the Company")
    job_description = job_details.get("job_description", "a specific role").strip() 
    job_title = job_details.get("job_title", job_details.get("role", "the Position")) 

    # 3. Construct the LLM Prompt
    
    # CRITICAL: Tell the LLM to skip the signature/salutation/signoff so we can control the format
    system_instruction = (
        EMAIL_SYSTEM_PROMPT + 
        "\n\nGOAL: Tailor the email content to show the applicant's match to the job requirements."
        "\nINSTRUCTIONS: 1. Start immediately with the first paragraph after the salutation (e.g., 'I am writing to express...'). 2. Mention the attached resume. 3. DO NOT include a salutation, signoff (e.g., 'Sincerely'), or signature block. Output only the body paragraphs."
    )

    user_prompt = f"""
    APPLICANT DETAILS: 
    - Name: {user_name}
    - Key Skills: Business Analytics, Python, SQL, Algorithms, AI, Machine Learning.

    JOB DETAILS:
    - Company: {company_name}
    - Role: {job_title}
    - Recipient (if known): {recruiter_name or 'Hiring Team'}
    - Full Job Description: {job_description}
    """

    # 4. Call Groq API
    try:
        response = client.chat.completions.create(
            model=EMAIL_MODEL_NAME, 
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.4 
        )
        llm_body_content = response.choices[0].message.content.strip()
        
    except Exception as e:
        # Fallback if API call fails for any other reason (e.g., networking, model error)
        print(f"[Groq Email Generator] Error during API call: {e}. Using fallback.")
        # return _generate_fallback_email(job_details, recruiter_name, user_name, user_phone, user_linkedin)
        
    # 5. Manually Construct Final Email Format
    
    # Salutation 
    salutation = f"Hi {recruiter_name or 'Hiring Team'},\n\n"
    
    # Signature Block
    signature_block = f"""
Best regards,

{user_name}
Phone No: {user_phone or "N/A"}
LinkedIn Link: {user_linkedin or "N/A"}
"""

    # Combine salutation, LLM body, and custom signature
    full_email_body = salutation + llm_body_content + signature_block
    
    # 6. Define a Standard Subject
    subject = f"Application for {job_title} | {user_name}"
    
    return full_email_body.strip(), subject

# def _generate_fallback_email(
#     job_details: Dict[str, str], 
#     recruiter_name: Optional[str], 
#     user_name: str, 
#     user_phone: Optional[str],
#     user_linkedin: Optional[str]
# ) -> Tuple[str, str]:
#     """Helper function to generate a basic email template if the API call fails."""
#     company_name = job_details.get("company_name", "the Company")
#     job_title = job_details.get("job_title", job_details.get("role", "the Position")) 

#     # --- Fallback Body ---
#     fallback_body_content = f"""
# I am writing to express my strong interest in the {job_title} position at {company_name}. My qualifications align perfectly with the requirements outlined in the job description.

# Please find my tailored resume attached for your consideration.

# Thank you for your time and consideration. I look forward to hearing from you.
# """
    
#     # --- Signature Block ---
#     # Using placeholder values for phone/linkedin in the fallback since they weren't passed
#     # and the LLM can't fill them.
#     signature_block = f"""
# Best regards,

# {user_name}
# Phone No: {user_phone or "N/A"}
# LinkedIn Link: {user_linkedin or "N/A"}
# """
    
#     # --- Full Email ---
#     full_email_body = f"Hi {recruiter_name or 'Hiring Team'},\n\n"
#     full_email_body += fallback_body_content.strip()
#     full_email_body += signature_block

#     subject = f"Application for {job_title} | {user_name}"
#     return full_email_body.strip(), subject
