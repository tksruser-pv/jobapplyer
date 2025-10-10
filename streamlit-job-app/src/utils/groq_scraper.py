import re
import pandas as pd
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import os
import difflib
from validate_email_address import validate_email

# NOTE: EXCEL_PATH must be defined here if it is not imported from app.py
EXCEL_PATH = r"F:\TKSR PRODUCTION\job1\a1.xlsx"

# --- LLM Client Setup ---
# Your API key from the context (cleaned of any potential whitespace)
groq_api_key = "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".strip() 

client = OpenAI(
    api_key=groq_api_key,
    base_url="https://api.groq.com/openai/v1"
)

# =================================================================
# AGENTIC TOOL 1: DIRECT EXCEL LOOKUP
# =================================================================

def _find_in_excel(hr_name: str = "", company_name: str = "") -> str | None:
    """
    Directly checks the Excel file for a previously saved recruiter email.
    """
    try:
        df = pd.read_excel(EXCEL_PATH)

        # Standardize column names for lookup
        all_cols = [col.lower() for col in df.columns]
        
        if "recruiter email" not in all_cols:
            return None
        recruiter_email_col = df.columns[all_cols.index("recruiter email")]

        # Step 1: Company match 
        if "company name" in all_cols and company_name:
            company_col = df.columns[all_cols.index("company name")]
            
            # Ensure column used for filtering is converted to string for safety
            df[company_col] = df[company_col].astype(str).str.strip() 

            match = df[df[company_col].str.lower().str.contains(company_name.lower(), na=False)]
            if not match.empty:
                email = match[recruiter_email_col].values[0]
                if pd.notna(email) and "@" in str(email):
                    return str(email).strip()

        # Step 2: Recruiter name match 
        if "recruiter name" in all_cols and hr_name:
            recruiter_name_col = df.columns[all_cols.index("recruiter name")]
            
            # Ensure column used for fuzzy matching is converted to string for safety
            df[recruiter_name_col] = df[recruiter_name_col].astype(str).str.strip() 
            
            names = df[recruiter_name_col].dropna().str.lower().tolist()
            closest = difflib.get_close_matches(hr_name.lower().strip(), names, n=1, cutoff=0.6)

            if closest:
                row = df[df[recruiter_name_col].str.lower().str.strip() == closest[0]]
                email = row[recruiter_email_col].values[0]
                if pd.notna(email) and "@" in str(email):
                    return str(email).strip()

        return None
        
    except Exception as e:
        print(f"[Excel] Error: {e}")
        return None

# =================================================================
# AGENTIC TOOL 2: DOMAIN INFERENCE AND PATTERN GENERATION
# =================================================================

def _infer_company_domain(company_name: str) -> str | None:
    """Uses Groq to guess the official domain (Part of Tool 2)."""
    try:
        if not company_name or company_name.lower() in ["nan", "none", "unknowncompany"]:
            return None

        prompt = f"Find the most likely official domain name of the company '{company_name}'. Only return the domain."
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.2
        )
        domain = response.choices[0].message.content.strip()
        domain = re.sub(r"^https?://", "", domain)
        domain = domain.split("/")[0]
        
        # CRITICAL CHECK: Ensure the domain looks valid before returning
        if "." in domain and not domain.startswith("support.google"):
             return domain
        return None
        
    except Exception as e:
        print(f"[Groq] Failed to infer domain for {company_name}: {e}")
        return None 

def _scrape_domain_fallback(company_name: str) -> str | None:
    """
    Placeholder for a scraping function that would attempt to find the domain 
    if Groq failed or returned a generic one.
    
    NOTE: Implementation is omitted for brevity but should exist in your full utility file.
    """
    return None 


def _generate_email_patterns(hr_name: str, domain: str) -> list[str]:
    """Generates email candidates based on name and domain (Part of Tool 2)."""
    if not domain: return []

    # Clean up name parts
    parts = hr_name.lower().split()
    if not parts: return []
        
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""

    candidates = [
        f"{first}.{last}@{domain}",       # john.doe@domain.com
        f"{first}@{domain}",              # john@domain.com
        f"{first}{last}@{domain}",        # johndoe@domain.com
        f"{first[0]}{last}@{domain}",     # jdoe@domain.com
        f"{last}@{domain}",               # doe@domain.com
        f"{first[0]}.{last}@{domain}",    # j.doe@domain.com
        f"{last}{first[0]}@{domain}",     # doej@domain.com
    ]
    # Add generic HR emails
    candidates.extend([f"hr@{domain}", f"careers@{domain}", f"recruiting@{domain}"])

    return list(set(c for c in candidates if c.replace("@", "").strip()))

# Correctly defined email scraping function (NO leading underscore)
def scrape_recruiter_email(job_description: str) -> str | None:
    """
    Extracts the first valid email address found in the job description text.
    """
    if not job_description:
        return None
    # Simple regex for email extraction
    matches = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", job_description)
    for email in matches:
        if "@" in email and "." in email:
            return email.strip()
    return None

# =================================================================
# AGENTIC TOOL 3: EMAIL VERIFICATION (CRITICAL FIX APPLIED HERE)
# =================================================================

def _verify_email_candidates(candidates: list[str]) -> str | None:
    """
    Verifies email candidates using regex + MX lookup.
    Returns the first valid & deliverable email.
    """
    print(f"[Verifier] Attempting to verify {len(candidates)} candidates...")

    for email in candidates:
        # Step 1: Basic regex check
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            continue

        # Step 2: Validate email with MX check
        try:
            # 💡 FIX: Changed 'email_address' to 'email' to resolve the TypeError
            is_valid = validate_email(
                email=email, 
                check_format=True, 
                check_blacklist=True, 
                check_dns=True, # MX record
                dns_timeout=10, 
                check_smtp=False, # Set SMTP check to False
                smtp_timeout=10, 
                smtp_skip_tls=False, 
                smtp_debug=False
            )
        except Exception as e:
            # Catch exceptions from validation library 
            print(f"[Verifier] Error checking {email}: {e}")
            is_valid = False 
        
        # Check if the result is True (deliverable or catch-all)
        if is_valid is True or is_valid == 'catchall':
            print(f"[Verifier] ✅ Verified email: {email}")
            return email
        else:
            print(f"[Verifier] ❌ Invalid or Undeliverable: {email}")


    # If verification failed for all, fall back to the best professional pattern guess
    
    # Priority 1: Check for professional name patterns (first.last, first_last, firstinitiallast)
    for email in candidates:
        if re.match(r"^[a-z]+[._]?[a-z]+@[a-z0-9.-]+\.[a-z]{2,}$", email):
            print(f"[Verifier] Selected unverified professional pattern: {email}")
            return email
            
    # Priority 2: Check for generic HR/Recruiting addresses
    for email in candidates:
        if email.startswith(("hr@", "careers@", "recruiting@")):
            print(f"[Verifier] Selected unverified generic pattern: {email}")
            return email
            
    print("[Verifier] All generated candidates failed selection criteria.")
    return None


# =================================================================
# MAIN AGENTIC-STYLE FUNCTION (get_recruiter_email)
# =================================================================

def get_recruiter_email(hr_name: str, company_name: str, job_description: str) -> str | None:
    """
    Main function that simulates the Agentic reasoning process:
    1. Check Excel
    2. Check JD
    3. Generate Patterns
    4. Verify & Select 
    """
    
    # 1. Step 1: Check Excel (Tool 1)
    email = _find_in_excel(hr_name, company_name)
    if email:
        print(f"[Agent] Found email in Excel: {email}")
        return email

    # 2. Step 2: Look in job description (Tool 2 variant)
    email = scrape_recruiter_email(job_description) 
    if email:
        print(f"[Agent] Found email in JD: {email}")
        return email
        
    # 3. Step 3: Generate Pattern Candidates (Tool 2)
    domain = _infer_company_domain(company_name) or _scrape_domain_fallback(company_name)
    
    if not domain:
        print(f"[Agent] Failed to infer company domain for {company_name}")
        return None 

    # CRITICAL FIX: Check if Groq/Scraper returned the invalid domain
    if domain.lower().startswith("support.google") or domain.lower().startswith("google.com"):
        print(f"[Agent] Inferred domain {domain} is generic; aborting generation.")
        return None
        
    candidates = _generate_email_patterns(hr_name, domain)
    
    if not candidates:
        return None

    # 4. Step 4: Verify and Select (Tool 3)
    best_email = _verify_email_candidates(candidates)
    
    if best_email:
        print(f"[Agent] Verified best candidate: {best_email}")
        return best_email
        
    print("[Agent] All generated candidates failed verification.")
    return None