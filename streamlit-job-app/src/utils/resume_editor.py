import os
import re
import configparser
from openai import OpenAI
from typing import Optional

# --- Conditional Imports (Required libraries for file reading) ---
# NOTE: Ensure you have 'pypdf' and 'python-docx' installed for this to work.
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

# =================================================================
# SIMULATED CONFIGURATION & CLIENT SETUP 
# (In the full agent, these would be loaded from config.ini)
# =================================================================

# The actual values would be loaded from your config.ini file:
# Example values for reference:
GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"
RESUME_MODEL_NAME = "llama-3.1-405b"
RESUME_SYSTEM_PROMPT = "You are a world-class career coach. Your task is to rewrite a user's resume (provided as text) to perfectly match a given job description. Focus on: 1. Highlighting relevant skills and keywords from the job description. 2. Tailoring bullet points to match the required duties. 3. Maintaining the original tone and structure of the resume. Output ONLY the complete, rewritten resume text in Markdown format. DO NOT include any introductory or concluding remarks."


client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =================================================================
# HELPER FUNCTION: TEXT EXTRACTION
# =================================================================

def _extract_text_from_doc(user_resume_path: str) -> str:
    """Helper to extract clean text from PDF or DOCX using available libraries."""
    file_extension = os.path.splitext(user_resume_path)[1].lower()
    
    if file_extension == '.pdf' and PdfReader:
        try:
            reader = PdfReader(user_resume_path)
            # Efficiently join text from all pages
            text = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
            return text if text else "ERROR: Could not extract text from PDF (Empty content)."
        except Exception as e:
            return f"ERROR: Failed to read PDF: {e}"

    elif file_extension == '.docx' and Document:
        try:
            doc = Document(user_resume_path)
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text)
            return text if text else "ERROR: Could not extract text from DOCX (Empty content)."
        except Exception as e:
            return f"ERROR: Failed to read DOCX: {e}"
    
    else:
        # Check if file format is unsupported or the required library is missing
        if not PdfReader and file_extension == '.pdf':
             return "ERROR: 'pypdf' library is missing. Cannot process PDF."
        if not Document and file_extension == '.docx':
             return "ERROR: 'python-docx' library is missing. Cannot process DOCX."
             
        return "ERROR: Unsupported file format. Please provide a PDF or Word document."


# =================================================================
# MAIN FUNCTION: EDIT RESUME
# =================================================================

def edit_resume(user_resume_path: str, job_description: str, output_path: str) -> str:
    """
    Tailors a resume to a job description using an LLM and saves the result as a Markdown file.
    
    This function intelligently rewrites the resume content using the LLM for high-quality,
    targeted output, saving the result in a reliable Markdown text format.
    """
    # Check if the API key is configured
    if not client.api_key:
        return "ERROR: Groq API key is required to use the resume editor. Please configure it in config.ini."
        
    # 1. Extract raw text from the user's resume file
    raw_resume_text = _extract_text_from_doc(user_resume_path)

    if raw_resume_text.startswith("ERROR"):
        return raw_resume_text

    print("Successfully extracted resume text. Calling LLM for rewrite...")

    # 2. Construct the prompt for the LLM
    user_prompt = f"""
    --- ORIGINAL RESUME TEXT ---
    {raw_resume_text}

    --- JOB DESCRIPTION ---
    {job_description}
    """
    
    # 3. Call the LLM to generate the modified resume
    try:
        response = client.chat.completions.create(
            model=RESUME_MODEL_NAME, 
            messages=[
                {"role": "system", "content": RESUME_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3, # Low temperature for reliable, structured output
        )
        modified_resume_text = response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"ERROR: LLM failed to generate modified resume. API Error: {e}"
        
    # 4. Save the modified text as a Markdown file
    if not output_path.lower().endswith(('.md', '.txt')):
        # Ensure the output is a standard text format for the LLM output
        output_path = os.path.splitext(output_path)[0] + '.md'

    try:
        with open(output_path, 'w', encoding='utf-8') as output_file:
            output_file.write(modified_resume_text)
        
        print(f"Successfully saved tailored resume to: {output_path}")
        return output_path
        
    except Exception as e:
        return f"ERROR: Failed to write output file: {e}"

def _load_config():
    config = configparser.ConfigParser()
    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.ini'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'config.ini'),
        os.path.join(os.getcwd(), 'config.ini'),
        os.path.join(os.getcwd(), 'config', 'config.ini'),
    ]
    # Search through the candidate locations and pick the first existing config file
    config_path = None
    for path in possible_paths:
        if os.path.exists(path):
            config_path = path
            break

    if not config_path or not config.read(config_path):
        # print("WARNING: config.ini not found. Using hardcoded values for resume editor.")
        return "YOUR_GROQ_API_KEY_HERE", "llama-3.1-405b", (
            "You are a world-class career coach. Your task is to rewrite a user's resume (provided as text) to perfectly match a given job description. "
            "Focus on: 1. Highlighting relevant skills and keywords from the job description. 2. Tailoring bullet points to match the required duties. "
            "3. Maintaining the original tone and structure of the resume. Output ONLY the complete, rewritten resume text in Markdown format. "
            "DO NOT include any introductory or concluding remarks."
        )

    try:
        groq_api_key = config['API_KEYS'].get('GROQ_API_KEY', "YOUR_GROQ_API_KEY_HERE").strip()
        resume_model_name = config['LLM_SETTINGS'].get('MODEL_NAME', "llama-3.1-405b")
        resume_system_prompt = config['LLM_SETTINGS'].get('RESUME_SYSTEM_PROMPT', (
            "You are a world-class career coach. Your task is to rewrite a user's resume (provided as text) to perfectly match a given job description. "
            "Focus on: 1. Highlighting relevant skills and keywords from the job description. 2. Tailoring bullet points to match the required duties. "
            "3. Maintaining the original tone and structure of the resume. Output ONLY the complete, rewritten resume text in Markdown format. "
            "DO NOT include any introductory or concluding remarks."
        ))
        return groq_api_key, resume_model_name, resume_system_prompt
    except KeyError as e:
        print(f"ERROR: Missing required key in config.ini: {e}. Using defaults.")
        return "YOUR_GROQ_API_KEY_HERE", "llama-3.1-405b", (
            "You are a world-class career coach. Your task is to rewrite a user's resume (provided as text) to perfectly match a given job description. "
            "Focus on: 1. Highlighting relevant skills and keywords from the job description. 2. Tailoring bullet points to match the required duties. "
            "3. Maintaining the original tone and structure of the resume. Output ONLY the complete, rewritten resume text in Markdown format. "
            "DO NOT include any introductory or concluding remarks."
        )

GROQ_API_KEY, RESUME_MODEL_NAME, RESUME_SYSTEM_PROMPT = _load_config()

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)
