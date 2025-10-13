import re
import pandas as pd
import os
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import difflib
from validate_email_address import validate_email

# =================================================================
# CONFIGURATION LOADING
# =================================================================

def _load_config():
    import configparser, os
    config = configparser.ConfigParser()
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

    if not config_path or not config.read(config_path):
        print("WARNING: config.ini not found. Using hardcoded path and skipping LLM setup.")
        return r"F:\TKSR PRODUCTION\job1\a1.xlsx", "", "llama-3.1-8b-instant", ""

    try:
        excel_path = config['PATHS'].get('EXCEL_PATH', r"F:\TKSR PRODUCTION\job1\a1.xlsx")
        groq_api_key = config['API_KEYS'].get('GROQ_API_KEY', "").strip()
        model_name = config['LLM_SETTINGS'].get('MODEL_NAME', "llama-3.1-8b-instant")
        domain_prompt = config['LLM_SETTINGS'].get('DOMAIN_INFERENCE_PROMPT', "What is the official, current, and exact website domain name (only the domain, no https/www, no slashes, no dots except before the TLD) for the company '{company_name}'. Only return the domain name.")
        return excel_path, groq_api_key, model_name, domain_prompt
    except KeyError as e:
        print(f"ERROR: Missing required key in config.ini: {e}. Using defaults.")
        return r"F:\TKSR PRODUCTION\job1\a1.xlsx", "", "llama-3.1-8b-instant", ""

# Load configuration and set global variables
EXCEL_PATH, groq_api_key, LLM_MODEL, DOMAIN_PROMPT = _load_config()


# --- LLM Client Setup ---
client = OpenAI(
    api_key=groq_api_key,
    base_url="https://api.groq.com/openai/v1"
)

# --- Utility to fix domains (Function carried over) ---
def _ensure_tld(domain: str) -> str:
    """Ensures the domain has a top-level domain (.com, .net, etc.) and is lowercase."""
    domain = domain.lower().strip()
    if not domain:
        return ""
    
    # Check if a TLD (a dot followed by 2 or more letters) is present
    if not re.search(r'\.[a-z]{2,}$', domain):
        print(f"[Domain Fix] Appending '.com' to incomplete domain: {domain}")
        return f"{domain}.com"
    
    return domain

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
            
            df[company_col] = df[company_col].astype(str).str.strip() 

            match = df[df[company_col].str.lower().str.contains(company_name.lower(), na=False)]
            if not match.empty:
                email = match[recruiter_email_col].values[0]
                if pd.notna(email) and "@" in str(email):
                    return str(email).strip()

        # Step 2: Recruiter name match 
        if "recruiter name" in all_cols and hr_name:
            recruiter_name_col = df.columns[all_cols.index("recruiter name")]
            
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
    """Uses Groq to guess the official domain (Part of Tool 2), with config variables and boilerplate rejection."""
    try:
        if not company_name or company_name.lower() in ["nan", "none", "unknowncompany"]:
            return None
        if not client.api_key:
             print("[Groq] API key not loaded, skipping LLM inference.")
             return None

        # Using config variables
        prompt = DOMAIN_PROMPT.format(company_name=company_name)
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30, 
            temperature=0.1 
        )
        domain = response.choices[0].message.content.strip()
        
        domain = re.sub(r"^https?://|/$", "", domain)
        domain = domain.split("/")[0]

        # FIX: Check for LLM boilerplate error messages
        boilerplate_patterns = [
            r'i am unable to verify',
            r'i cannot provide',
            r'not available',
            r'domain name for',
            r'no domain'
        ]
        if any(re.search(pattern, domain.lower()) for pattern in boilerplate_patterns):
            print(f"[Groq] LLM output rejected as boilerplate: {domain}")
            return None
        
        # FIX: Check and fix domain before validating/rejecting
        if "." not in domain or len(domain.split(".")) < 2:
            cleaned_domain = _ensure_tld(domain)
            if cleaned_domain and "." in cleaned_domain:
                print(f"[Groq] LLM output fixed to: {cleaned_domain}")
                return cleaned_domain
                
            print(f"[Groq] LLM output rejected as non-domain: {domain}")
            return None
            
        # FIX: Ensure the final domain is clean
        final_domain = _ensure_tld(domain)
        print(f"[Groq] LLM inferred domain: {final_domain}")
        return final_domain
        
    except Exception as e:
        print(f"[Groq] Failed to infer domain for {company_name}: {e}")
        return None

def _scrape_domain_fallback(company_name: str) -> str | None:
    """
    Scrapes Google search results to extract a domain (Tool 2, Primary Check).
    (Includes FIX for missing TLD).
    """
    try:
        query = f"{company_name} official website"
        url = f"https://www.google.com/search?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        
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
                    # FIX: Apply the cleanup function before returning
                    final_domain = _ensure_tld(domain)
                    print(f"[Scraper] Found primary domain: {final_domain}")
                    return final_domain
        return None
    except Exception as e:
        print(f"[Scraper] Domain check failed for {company_name}: {e}")
        return None 


def _generate_email_patterns(hr_name: str, domain: str) -> list[str]:
    """
    Generates email candidates based ONLY on the corporate domain.
    The gmail.com logic has been removed.
    """
    if not hr_name: return []

    # Logic only includes the corporate domain
    domains_to_check = []
    
    # 1. Add the inferred/scraped corporate domain (e.g., chetu.com)
    if domain:
        domains_to_check.append(domain)
        
    # If no domain is found, we cannot generate patterns
    if not domains_to_check: return []
        
    # Clean up name parts
    parts = hr_name.lower().split()
    if not parts: return []
        
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    
    candidates = []

    # Iterate through all domains (should only be the corporate domain)
    for d in domains_to_check:
        # Standard name-based professional patterns
        candidates.extend([
            f"{first}.{last}@{d}",       # john.doe@domain.com
            f"{first}@{d}",              # john@domain.com
            f"{first}{last}@{d}",        # johndoe@domain.com
            f"{first[0]}{last}@{d}",     # jdoe@domain.com
            f"{last}@{d}",               # doe@domain.com
            f"{first[0]}{last[0]}@{d}",  # j.d@domain.com
        ])
        
    # Add generic HR emails ONLY for the company domain
    if domain:
        candidates.extend([f"hr@{domain}", f"careers@{domain}", f"recruiting@{domain}"])

    # Remove duplicates and ensure clean candidates before verification
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
            is_valid = validate_email(
                email=email, 
                check_format=True, 
                check_blacklist=True, 
                check_dns=True, # MX record
                dns_timeout=10, 
                check_smtp=False, # Set SMTP check to False
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
    3. Find Domain (Scraper then LLM, with fixes)
    4. Generate Patterns (Corporate ONLY)
    5. Verify & Select 
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
        
    # 3. Step 3: Find Domain (Scraper then LLM)
    print(f"[Agent] Attempting domain scrape for {company_name}...")
    final_domain = _scrape_domain_fallback(company_name)
    
    if not final_domain:
        print(f"[Agent] Scraper failed. Falling back to LLM inference (strict mode)...")
        final_domain = _infer_company_domain(company_name)
    
    if not final_domain:
        print(f"[Agent] Failed to find a valid company domain for {company_name}. Aborting email generation.")
        return None
    
    # CRITICAL FIX: Check if LLM/Scraper returned a generic domain
    if "google.com" in final_domain.lower() or "linkedin.com" in final_domain.lower() or "wikipedia.org" in final_domain.lower():
         print(f"[Agent] Inferred domain {final_domain} is generic; aborting email generation.")
         return None
        
    print(f"[Agent] Using final corporate domain: {final_domain}")

    # 4. Step 4: Generate Patterns (Corporate ONLY)
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