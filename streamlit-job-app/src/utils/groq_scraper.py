import re
import pandas as pd
import os
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import difflib
from validate_email_address import validate_email

# NOTE: EXCEL_PATH must be defined here if it is not imported from app.py
EXCEL_PATH = r"F:\TKSR PRODUCTION\job1\a1.xlsx"

groq_api_key = "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".strip()

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
    Directly checks the Excel file for a previously saved recruiter email.
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
    """
    Uses Groq to guess the official domain (Tool 2, Fallback) with strict prompting.
    This logic has been updated to use a low temperature and strict prompt.
    """
    try:
        if not company_name or company_name.lower() in ["nan", "none", "unknowncompany"]:
            return None
        if not client.api_key:
             # Ensure the API key is set in your environment
             print("[Groq] API key not loaded, skipping LLM inference.")
             return None
            
        # 💡 NEW: Strict prompt and low temperature for deterministic output
        prompt = f"What is the official, current, and exact website domain name (only the domain, no https/www, no slashes, no dots except before the TLD) for the company '{company_name}'. Only return the domain name."
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30, 
            temperature=0.1 # Lowered temperature for deterministic output
        )
        domain = response.choices[0].message.content.strip()
        
        # Clean and validate the output to ensure it's a domain
        domain = re.sub(r"^https?://|/$", "", domain) # Remove common prefixes/suffixes
        domain = domain.split("/")[0] # Ensure no paths
        
        # Simple domain validation to reject non-domains like "I cannot provide..."
        if "." not in domain or len(domain.split(".")) < 2:
             print(f"[Groq] LLM output rejected as non-domain: {domain}")
             return None
             
        print(f"[Groq] LLM inferred domain: {domain}")
        return domain
        
    except Exception as e:
        print(f"[Groq] Failed to infer domain for {company_name}: {e}")
        return None


def _scrape_domain_fallback(company_name: str) -> str | None:
    """
    Scrapes Google search results to extract a domain (Tool 2, Primary Check).
    NOTE: This is prone to Google blocking (HTTP 403/429 errors).
    """
    try:
        query = f"{company_name} official website"
        url = f"https://www.google.com/search?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        
        # Using standard Python requests for web scraping
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code != 200:
            print(f"[Scraper] Failed to fetch search results (Status: {res.status_code})")
            return None

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Extract links from the search results
        links = [h3.parent['href'] for h3 in soup.select('h3') if h3.parent.has_attr('href')]

        for link in links:
            # Extract the domain from the URL
            match = re.search(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", link)
            if match:
                domain = match.group(1).lower()
                
                # General Fallback: Return the first non-generic domain.
                if "linkedin" not in domain and "google" not in domain and "wikipedia" not in domain:
                    print(f"[Scraper] Found primary domain: {domain}")
                    return domain
        return None
    except Exception as e:
        print(f"[Scraper] Domain check failed for {company_name}: {e}")
        return None


def _generate_email_patterns(hr_name: str, domain: str) -> list[str]:
    """Generates email candidates based on name and domain (Part of Tool 2)."""
    if not domain: return []

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
        f"{first[0]}{last[0]}@{domain}",  # j.d@domain.com
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
# AGENTIC TOOL 3: EMAIL VERIFICATION
# =================================================================

def _verify_email_candidates(candidates: list[str]) -> str | None:
    """
    Verifies email candidates using regex + MX lookup.
    """
    print(f"[Verifier] Attempting to verify {len(candidates)} candidates...")

    for email in candidates:
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            continue 

        # Using 'email=email' to resolve previous TypeError
        try:
            is_valid = validate_email(
                email=email, 
                check_format=True, 
                check_blacklist=True, 
                check_dns=True,       # MX record
                dns_timeout=10, 
                check_smtp=False,     # Set SMTP check to False for speed/reliability
            )
        except Exception as e:
            print(f"[Verifier] Error checking {email}: {e}")
            continue

        if is_valid is True or is_valid == 'catchall':
            print(f"[Verifier] ✅ Verified email: {email}")
            return email
        else:
            print(f"[Verifier] ❌ Invalid or Undeliverable: {email}")
            
    # Fallback logic: prioritize professional patterns, then generic HR, then any valid-looking email.
    for email in candidates:
        if re.match(r"^[a-z]+[._]?[a-z]+@[a-z0-9.-]+\.[a-z]{2,}$", email):
            print(f"[Verifier] Selected professional pattern: {email}")
            return email
            
    for email in candidates:
        if email.startswith(("hr@", "careers@", "recruiting@")):
            print(f"[Verifier] Selected generic pattern: {email}")
            return email
            
    for email in candidates:
        if re.match(r"[^@]+@[^@]+\.[^@]+", email):
            print(f"[Verifier] Selected fallback email: {email}")
            return email

    print("[Verifier] All generated candidates failed selection criteria.")
    return None

# =================================================================
# MAIN AGENTIC-STYLE FUNCTION (Scraper First, then LLM)
# =================================================================

def get_recruiter_email(hr_name: str, company_name: str, job_description: str) -> str | None:
    """
    Main function with the requested logic:
    1. Check Excel
    2. Check JD
    3. Scrape Domain (Primary)
    4. LLM Guess Domain (Fallback - now with strict prompt/low temp)
    5. Generate & Verify
    """
    
    # 1. Step 1: Check Excel (Highest confidence)
    email = _find_in_excel(hr_name, company_name)
    if email:
        print(f"[Agent] Found email in Excel: {email}")
        return email

    # 2. Step 2: Look in job description (High confidence)
    email = scrape_recruiter_email(job_description)
    if email:
        print(f"[Agent] Found email in JD: {email}")
        return email
        
    # 3. Step 3: Scrape Domain (Primary)
    print(f"[Agent] Attempting domain scrape for {company_name}...")
    final_domain = _scrape_domain_fallback(company_name)
    
    if not final_domain:
        # 4. Step 4: LLM Guess Domain (Fallback)
        print(f"[Agent] Scraper failed. Falling back to LLM inference (strict mode)...")
        final_domain = _infer_company_domain(company_name)
    
    if not final_domain:
        print(f"[Agent] Failed to find a valid company domain for {company_name}")
        return None 
    
    print(f"[Agent] Using final domain: {final_domain}")
    
    candidates = _generate_email_patterns(hr_name, final_domain)
    
    if not candidates:
        return None

    # 5. Step 5: Verify and Select (Tool 3)
    best_email = _verify_email_candidates(candidates)
    
    if best_email:
        print(f"[Agent] Verified best candidate: {best_email}")
        return best_email
        
    print("[Agent] All generated candidates failed verification.")
    return None