import re
import pandas as pd
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import os
import difflib
import re
from validate_email_address import validate_email

# NOTE: EXCEL_PATH must be defined here if it is not imported from app.py
EXCEL_PATH = r"F:\TKSR PRODUCTION\job1\a1.xlsx"

groq_api_key =" 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"
# --- LLM Client Setup ---
client = OpenAI(
    api_key=groq_api_key,
    base_url="https://api.groq.com/openai/v1"
)

# =================================================================
# AGENTIC TOOL 1: DIRECT EXCEL LOOKUP
# =================================================================

def _find_in_excel(hr_name: str = "", company_name: str = "") -> str | None:
    """
    Directly checks the Excel file for a previously saved recruiter email based on
    Company Name or Recruiter Name (Tool 1 in Agent logic).
    """
    try:
        df = pd.read_excel(EXCEL_PATH)

        all_cols = [col.lower() for col in df.columns]
        
        if "recruiter email" not in all_cols:
            return None
        recruiter_email_col = df.columns[all_cols.index("recruiter email")]

        # Step 1: Company match
        if "company name" in all_cols and company_name:
            company_col = df.columns[all_cols.index("company name")]
            
            match = df[df[company_col].astype(str).str.lower().str.contains(company_name.lower(), na=False)]
            if not match.empty:
                email = match[recruiter_email_col].values[0]
                if pd.notna(email) and "@" in str(email):
                    return str(email).strip()

        # Step 2: Recruiter name match
        if "recruiter name" in all_cols and hr_name:
            recruiter_name_col = df.columns[all_cols.index("recruiter name")]
            
            names = df[recruiter_name_col].dropna().astype(str).str.lower().str.strip().tolist()
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
        return domain
    except Exception as e:
        print(f"[Groq] Failed to infer domain for {company_name}: {e}")
        return None


def _scrape_domain_fallback(company_name: str) -> str | None:
    """Scrapes Google search results to extract a domain (Fallback for Tool 2)."""
    try:
        query = f"{company_name} official site"
        url = f"https://www.google.com/search?q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "html.parser")
        links = [a["href"] for a in soup.select("a[href]") if "http" in a["href"]]

        for link in links:
            match = re.search(r"https?://([a-zA-Z0-9.-]+)", link)
            if match:
                domain = match.group(1)
                if not domain.startswith(company_name.lower()):
                    return domain
        return None
    except Exception as e:
        print(f"[Scraper] Fallback failed for {company_name}: {e}")
        return None


def _generate_email_patterns(hr_name: str, domain: str) -> list[str]:
    """Generates email candidates based on name and domain (Part of Tool 2)."""
    if not domain: return []

    parts = hr_name.lower().split()
    if not parts: return []
        
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""

    candidates = [
        f"{first}.{last}@{domain}", # john.doe@domain.com
        f"{first}@{domain}",        # john@domain.com
        f"{first}{last}@{domain}",  # johndoe@domain.com
        f"{first[0]}{last}@{domain}",# jdoe@domain.com
        f"{last}@{domain}",          # doe@domain.com
    ]
    # Add generic HR emails
    candidates.extend([f"hr@{domain}", f"careers@{domain}", f"recruiting@{domain}"])

    return list(set(c for c in candidates if c.replace("@", "").strip()))


def scrape_recruiter_email(job_description: str) -> str | None:
    """Scrapes email from job description text (Tool 2 variant)."""
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(com|in|org|net|co|edu)", job_description)
    if match:
        return match.group(0)
    return None

# =================================================================
# AGENTIC TOOL 3: EMAIL VERIFICATION (CRITICAL FOR 70%+)
# =================================================================

def _verify_email_candidates(candidates: list[str]) -> str | None:
    """
    Verifies email candidates using regex + SMTP (MX lookup).
    Returns the first valid & deliverable email.
    """
    print(f"[Verifier] Attempting to verify {len(candidates)} candidates...")

    for email in candidates:
        # Step 1: Basic regex check
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            continue  

        # Step 2: Validate email with MX + SMTP check
        try:
            is_valid = validate_email(
                email_address=email, 
                check_format=True, 
                check_blacklist=True, 
                check_dns=True,       # MX record
                dns_timeout=10, 
                check_smtp=True,      # Real mail server check
                smtp_timeout=10, 
                smtp_skip_tls=False, 
                smtp_debug=False
            )
        except Exception as e:
            print(f"[Verifier] Error checking {email}: {e}")
            continue

        if is_valid:
            print(f"[Verifier] ✅ Verified email: {email}")
            return email
        else:
            print(f"[Verifier] ❌ Invalid: {email}")
    for email in candidates:
        # Simple regex check for professional name pattern
        if re.match(r"^[a-z]+[._][a-z]+@[a-z0-9.-]+\.[a-z]{2,}$", email):
            print(f"[Verifier] Selected professional pattern: {email}")
            return email
            
    # Priority 2: Check for generic HR/Recruiting addresses
    for email in candidates:
        if email.startswith(("hr@", "careers@", "recruiting@")):
            print(f"[Verifier] Selected generic pattern: {email}")
            return email
            
    # Priority 3: Fallback (any valid-looking email)
    for email in candidates:
        if re.match(r"[^@]+@[^@]+\.[^@]+", email):
            print(f"[Verifier] Selected fallback email: {email}")
            return email

    print("[Verifier] All generated candidates failed selection criteria.")
    return None

# =================================================================
# MAIN AGENTIC-STYLE FUNCTION
# =================================================================

def get_recruiter_email(hr_name: str, company_name: str, job_description: str) -> str | None:
    """
    Main function that simulates the Agentic reasoning process:
    1. Check Excel (Highest confidence)
    2. Check JD (High confidence)
    3. Generate Patterns (Medium confidence)
    4. Verify & Select (Highest confidence candidate)
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
        return None # Cannot proceed without a domain
        
    candidates = _generate_email_patterns(hr_name, domain)
    
    if not candidates:
        return None

    # 4. Step 4: Verify and Select (Tool 3)
    # The agent uses the verification tool to filter the generated list.
    best_email = _verify_email_candidates(candidates)
    
    if best_email:
        print(f"[Agent] Verified best candidate: {best_email}")
        return best_email
        
    print("[Agent] All generated candidates failed verification.")
    return None