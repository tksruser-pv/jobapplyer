import re
import pandas as pd
import os
import sys
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import difflib
from validate_email_address import validate_email

# =================================================================
# GLOBAL CONFIGURATION AND UTILITIES
# =================================================================

# Simple logging utility
def _log(level: str, message: str):
    """Prints a standardized log message."""
    # Using sys.stderr for error messages, sys.stdout for others (info/debug)
    if level.upper() == 'ERROR':
        print(f"[{level.upper()}]: {message}", file=sys.stderr)
    else:
        print(f"[{level.upper()}]: {message}", file=sys.stdout)

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
        _log('WARNING', "config.ini not found. Using hardcoded path and skipping LLM setup.")
        # Return defaults for paths and empty string for keys/prompts
        return r"F:\TKSR PRODUCTION\job1\a1.xlsx", "", "llama-3.1-8b-instant", ""

    try:
        excel_path = config['PATHS'].get('EXCEL_PATH', r"F:\TKSR PRODUCTION\job1\a1.xlsx")
        groq_api_key = config['API_KEYS'].get('GROQ_API_KEY', "").strip()
        model_name = config['LLM_SETTINGS'].get('MODEL_NAME', "llama-3.1-8b-instant")
        # Ensure DOMAIN_INFERENCE_PROMPT is retrieved cleanly
        domain_prompt = config['LLM_SETTINGS'].get('DOMAIN_INFERENCE_PROMPT', 
            "What is the official, current, and exact website domain name (only the domain, no https/www, no slashes, no dots except before the TLD) for the company '{company_name}'. Only return the domain name.")
            
        return excel_path, groq_api_key, model_name, domain_prompt
    except KeyError as e:
        _log('ERROR', f"Missing required key in config.ini: {e}. Using defaults.")
        return r"F:\TKSR PRODUCTION\job1\a1.xlsx", "", "llama-3.1-8b-instant", ""

# Load configuration and set global variables
EXCEL_PATH, groq_api_key, LLM_MODEL, DOMAIN_PROMPT = _load_config()


# --- LLM Client Setup ---
client = OpenAI(
    api_key=groq_api_key,
    base_url="https://api.groq.com/openai/v1"
)

# --- Utility to fix domains ---
def _ensure_tld(domain: str) -> str:
    """
    Ensures the domain has a top-level domain, is lowercase, 
    and strips common prefixes/suffixes.
    """
    domain = domain.lower().strip()
    if not domain:
        return ""
    
    # Strip common prefixes (http, www) and path suffixes
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split('/')[0].split('?')[0] # Remove path and query params

    # Check if a TLD (a dot followed by 2 or more letters) is present
    if not re.search(r'\.[a-z]{2,}$', domain):
        _log('DEBUG', f"[Domain Fix] Appending '.com' to incomplete domain: {domain}")
        return f"{domain}.com"
    
    return domain

# =================================================================
# AGENTIC TOOL 1: DIRECT EXCEL LOOKUP
# =================================================================

def _find_in_excel(hr_name: str = "", company_name: str = "") -> str | None:
    """
    Directly checks the Excel file for a previously saved recruiter email.
    """
    if not os.path.exists(EXCEL_PATH):
        _log('WARNING', f"[Excel] Excel file not found at path: {EXCEL_PATH}")
        return None
        
    try:
        df = pd.read_excel(EXCEL_PATH)

        # Standardize column names for lookup
        col_map = {col.lower().strip(): col for col in df.columns}
        
        recruiter_email_col = col_map.get("recruiter email")
        if not recruiter_email_col:
            _log('DEBUG', "[Excel] 'Recruiter Email' column not found.")
            return None

        # Step 1: Company match 
        if "company name" in col_map and company_name:
            company_col = col_map["company name"]
            
            # Ensure the column is string and strip surrounding whitespace
            df[company_col] = df[company_col].astype(str).str.strip() 

            # Use case-insensitive partial match
            match = df[df[company_col].str.lower().str.contains(company_name.lower(), na=False)]
            if not match.empty:
                email = match[recruiter_email_col].iloc[0] # Use iloc[0] instead of values[0] for robustness
                if pd.notna(email) and "@" in str(email):
                    _log('INFO', f"[Excel] Found company match for '{company_name}'.")
                    return str(email).strip()

        # Step 2: Recruiter name match 
        if "recruiter name" in col_map and hr_name:
            recruiter_name_col = col_map["recruiter name"]
            
            df[recruiter_name_col] = df[recruiter_name_col].astype(str).str.strip() 
            
            names = df[recruiter_name_col].dropna().str.lower().tolist()
            # Relax cutoff slightly for better fuzzy matching
            closest = difflib.get_close_matches(hr_name.lower().strip(), names, n=1, cutoff=0.7)

            if closest:
                # Find the row matching the closest name (case-insensitive and stripped)
                row = df[df[recruiter_name_col].str.lower().str.strip() == closest[0]]
                if not row.empty:
                    email = row[recruiter_email_col].iloc[0]
                    if pd.notna(email) and "@" in str(email):
                        _log('INFO', f"[Excel] Found fuzzy name match for '{hr_name}'. Closest: {closest[0]}.")
                        return str(email).strip()

        return None
        
    except Exception as e:
        _log('ERROR', f"[Excel] Error during lookup: {e}")
        return None

# =================================================================
# AGENTIC TOOL 2: DOMAIN INFERENCE AND PATTERN GENERATION
# =================================================================

def _infer_company_domain(company_name: str) -> str | None:
    """Uses Groq to guess the official domain (Part of Tool 2)."""
    try:
        if not company_name or company_name.lower() in ["nan", "none", "unknowncompany"]:
            return None
        if not client.api_key:
             _log('WARNING', "[Groq] API key not loaded, skipping LLM inference.")
             return None

        prompt = DOMAIN_PROMPT.format(company_name=company_name)
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30, 
            temperature=0.1 
        )
        domain = response.choices[0].message.content.strip()
        
        # Aggressive cleanup
        domain = _ensure_tld(domain)

        # FIX: Check for LLM boilerplate error messages
        boilerplate_patterns = [
            r'i am unable to verify', r'i cannot provide', r'not available', 
            r'domain name for', r'no domain', r'official website', r'i do not have',
            r'^the domain name', r'^www\.'
        ]
        if any(re.search(pattern, domain.lower()) for pattern in boilerplate_patterns):
            _log('WARNING', f"[Groq] LLM output rejected as boilerplate: {domain}")
            return None
        
        # Check if the cleaned domain is still valid (e.g., prevents "the.com" or "ask.com")
        if "." not in domain or len(domain.split(".")) < 2:
            _log('WARNING', f"[Groq] LLM output rejected as non-domain: {domain}")
            return None
            
        _log('INFO', f"[Groq] LLM inferred domain: {domain}")
        return domain
        
    except Exception as e:
        _log('ERROR', f"[Groq] Failed to infer domain for {company_name}: {e}")
        return None

def _scrape_domain_fallback(company_name: str) -> str | None:
    """
    Scrapes Google search results to extract a domain (Tool 2, Primary Check).
    """
    try:
        query = f"{company_name} official website"
        url = f"https://www.google.com/search?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        
        res = requests.get(url, headers=headers, timeout=15) # Increased timeout
        
        if res.status_code != 200:
            _log('WARNING', f"[Scraper] Failed to fetch search results (Status: {res.status_code})")
            return None

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Extract links from the search results
        # Targeting the URL visible in the search snippet (often under <cite> or the link itself)
        links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith('http')]

        for link in links:
            # Extract the domain from the URL
            match = re.search(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", link)
            if match:
                domain = match.group(1).lower()
                
                # Exclude generic or social media domains
                if not any(generic in domain for generic in ["linkedin", "google", "wikipedia", "facebook", "twitter", "indeed", "glassdoor"]):
                    # Apply the cleanup function before returning
                    final_domain = _ensure_tld(domain)
                    _log('INFO', f"[Scraper] Found primary domain: {final_domain}")
                    return final_domain
        return None
    except Exception as e:
        _log('ERROR', f"[Scraper] Domain check failed for {company_name}: {e}")
        return None 


def _generate_email_patterns(hr_name: str, domain: str) -> list[str]:
    """
    Generates professional email candidates based ONLY on the corporate domain.
    Includes enhanced name parsing.
    """
    if not hr_name or not domain: return []
    
    # Use only the corporate domain
    d = domain.lower()
        
    # Clean up name parts and handle middle names/initials
    parts = [p.strip() for p in hr_name.lower().split() if p.strip()]
    if not parts: return []
        
    first = parts[0]
    # Check for middle names/initials
    if len(parts) > 2:
        last = parts[-1]
        middle = parts[1:-1] # Elements between first and last
        m_initial = "".join([m[0] for m in middle])
    elif len(parts) == 2:
        first, last = parts
        middle = None
        m_initial = ""
    else: # Only one name part (use it as first, last is empty)
        first = parts[0]
        last = ""
        middle = None
        m_initial = ""

    f_initial = first[0] if first else ""
    l_initial = last[0] if last else ""
    
    candidates = []

    # Standard professional patterns
    if first and last:
        candidates.extend([
            f"{first}.{last}@{d}",          # john.doe@domain.com
            f"{f_initial}{last}@{d}",       # jdoe@domain.com
            f"{first}{l_initial}@{d}",      # john.d@domain.com - added
            f"{first}{last}@{d}",           # johndoe@domain.com (no dot)
            f"{f_initial}.{last}@{d}",      # j.doe@domain.com - added
            f"{last}.{first}@{d}",          # doe.john@domain.com - added
        ])
        if m_initial:
            candidates.extend([
                f"{f_initial}.{m_initial}.{last}@{d}", # j.a.doe@domain.com
                f"{first}{m_initial}{last}@{d}",       # jadoe@domain.com
            ])

    # Fallback/alternative patterns (when name is less formal or only one part is available)
    if first:
        candidates.append(f"{first}@{d}")
    if last:
        candidates.append(f"{last}@{d}")

    # Add generic HR emails 
    candidates.extend([f"hr@{d}", f"careers@{d}", f"recruiting@{d}", f"jobs@{d}"])

    # Remove duplicates and ensure clean candidates before verification
    # Using list comprehension to filter out empty strings
    return list(set(c for c in candidates if c.replace("@", "").strip()))

# Correctly defined email scraping function (NO leading underscore)
def scrape_recruiter_email(job_description: str) -> str | None:
    """
    Extracts the first valid email address found in the job description text.
    """
    if not job_description:
        return None
        
    # Improved regex to be slightly more comprehensive but still safe
    matches = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", job_description)
    
    for email in matches:
        if validate_email(email, check_format=True, check_dns=False): # Only check format here
            _log('INFO', f"[JD Scrape] Found valid-format email in JD: {email}")
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
    _log('INFO', f"[Verifier] Attempting to verify {len(candidates)} candidates...")
    
    verified_email = None

    for email in candidates:
        # Step 1: Basic format check (redundant but safe)
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            continue

        # Step 2: Validate email with MX check
        try:
            # check_smtp=False is crucial as it avoids sending emails or blocking on port 25
            is_valid = validate_email(
                email=email, 
                check_format=True, 
                check_blacklist=True, 
                check_dns=True, # MX record lookup
                dns_timeout=10, 
                check_smtp=False, 
            )
        except Exception as e:
            _log('ERROR', f"[Verifier] Error checking {email}: {e}")
            is_valid = False 
        
        # Check if the result is True (deliverable) or 'catchall' (likely deliverable)
        if is_valid is True or is_valid == 'catchall':
            _log('INFO', f"[Verifier] ✅ Verified email: {email} (Status: {is_valid})")
            return email
        else:
            _log('DEBUG', f"[Verifier] ❌ Invalid or Undeliverable: {email} (Status: {is_valid})")

    _log('WARNING', "[Verifier] No candidates passed MX verification. Falling back to best professional guess.")
    
    # --- FALLBACK LOGIC (Prioritize professional patterns) ---
    
    # 1. Look for common professional patterns (first.last, firstinitial.last)
    professional_patterns = [
        r"^[a-z]+\.[a-z]+@",            # first.last
        r"^[a-z]\.[a-z]+@",             # f.last
        r"^[a-z]+[._]?[a-z][._]?[a-z]+@" # f.m.l or fml etc.
    ]
    for email in candidates:
        domain_part = email.split('@')[1]
        if any(re.match(pattern, email) for pattern in professional_patterns) and not domain_part.startswith(("gmail", "yahoo", "outlook")):
             _log('INFO', f"[Verifier] Selected unverified professional pattern: {email}")
             return email
            
    # 2. Check for generic HR/Recruiting addresses
    for email in candidates:
        if email.startswith(("hr@", "careers@", "recruiting@", "jobs@")):
            _log('INFO', f"[Verifier] Selected unverified generic pattern: {email}")
            return email
            
    _log('WARNING', "[Verifier] All generated candidates failed selection criteria.")
    return None


# =================================================================
# MAIN AGENTIC-STYLE FUNCTION (get_recruiter_email)
# =================================================================

def get_recruiter_email(hr_name: str, company_name: str, job_description: str) -> str | None:
    """
    Main function that simulates the Agentic reasoning process:
    1. Check Excel (Historical Data)
    2. Check JD (Direct Scrape)
    3. Find Domain (Scraper then LLM)
    4. Generate Patterns (Corporate ONLY)
    5. Verify & Select (MX Check + Fallback)
    """
    
    _log('INFO', f"--- Starting Email Search for {hr_name} at {company_name} ---")

    # 1. Step 1: Check Excel (Tool 1)
    email = _find_in_excel(hr_name, company_name)
    if email:
        _log('SUCCESS', f"[Agent] Found email in Excel: {email}")
        return email

    # 2. Step 2: Look in job description (Tool 2 variant)
    email = scrape_recruiter_email(job_description) 
    if email:
        _log('SUCCESS', f"[Agent] Found email in JD: {email}")
        return email
        
    # 3. Step 3: Find Domain (Scraper then LLM)
    _log('INFO', f"[Agent] Attempting domain scrape for '{company_name}'...")
    final_domain = _scrape_domain_fallback(company_name)
    
    if not final_domain:
        _log('INFO', f"[Agent] Scraper failed. Falling back to LLM inference...")
        final_domain = _infer_company_domain(company_name)
    
    if not final_domain:
        _log('WARNING', f"[Agent] Failed to find a valid company domain for '{company_name}'. Aborting email generation.")
        return None
    
    # CRITICAL FIX: Check if LLM/Scraper returned a generic domain
    if any(generic in final_domain.lower() for generic in ["google.com", "linkedin.com", "wikipedia.org", "yahoo.com", "gmail.com"]):
        _log('WARNING', f"[Agent] Inferred domain '{final_domain}' is generic; aborting email generation.")
        return None
        
    _log('INFO', f"[Agent] Using final corporate domain: {final_domain}")

    # 4. Step 4: Generate Patterns (Corporate ONLY)
    candidates = _generate_email_patterns(hr_name, final_domain)
    
    if not candidates:
        _log('WARNING', "[Agent] No email candidates generated.")
        return None

    # 5. Step 5: Verify and Select (Tool 3)
    best_email = _verify_email_candidates(candidates)
    
    if best_email:
        _log('SUCCESS', f"[Agent] Final verified/guessed email: {best_email}")
        return best_email
        
    _log('ERROR', "[Agent] All agentic steps failed to provide a suitable email.")
    return None

