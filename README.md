# 🚀 AI-Powered Job Application Portal
**Automate, Customize, and Send Job Applications in Seconds**

This Streamlit-based **AI Job Application Assistant** streamlines your entire job application process — from managing job data to customizing resumes and sending personalized emails — all powered by **Groq’s LLM and secure Gmail integration**.

---

## ✨ Key Features  

### 📊 Excel-Based Job Management  
Easily read and manage all job details (company, recruiter name, job description, etc.) from a single Excel file (`a1.xlsx`).  

### 📅 Date-Based Filtering  
Filter jobs by specific dates to handle applications in organized daily batches.  

### 🧠 AI Resume Customization (LLM Integration)  
Automatically tailor your resume to each job description using a Large Language Model — creating highly personalized and targeted resumes for every application.  

### 🔍 Recruiter Email Finder  
Find or verify recruiter email addresses using built-in logic and **Groq/LLM-based scraping utilities**.  

### 📧 Automated Personalized Emails  
Send custom job applications directly via Gmail — with personalized text and the AI-edited resume attached (in Markdown format).  

### 🔐 Secure Gmail Authentication  
Uses **Google App Passwords** for safe SMTP login — keeping your credentials secure while ensuring automated mail dispatch.

---

## ⚙️ Installation & Setup Guide  

Follow these steps to set up and run the project locally 👇  

### 1️⃣ Prerequisites  
- Python **3.8 or higher** must be installed.  
- A valid **Groq API key** (`sk_live_...`)  
- A **Gmail App Password** (requires 2-Step Verification enabled on your Google account).  

---

### 2️⃣ Clone the Repository  

```bash
git clone https://github.com/tksruser-pv/jobapplyer.git
cd jobapplyer
```

---

### 3️⃣ Install Dependencies  

Install all required Python packages:  
```bash
pip install -r requirements.txt
```

---

### 4️⃣ Configure Your Settings  

Create a `config.ini` file in your project root and define essential paths and keys.  

#### 🧩 Example `config.ini`  

```ini
[PATHS]
# REQUIRED: Update this path to your job tracking Excel file
EXCEL_PATH = F:\TKSR PRODUCTION\job1\a1.xlsx

[API_KEYS]
# REQUIRED: Replace with your actual Groq API key
GROQ_API_KEY = sk_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

### 5️⃣ Required Tokens & Credentials  

| **Token Type** | **Purpose** | **How to Obtain It** |
|----------------|--------------|-----------------------|
| **Groq API Key** | Powers AI-based resume editing & email content generation. | Get it from the [Groq Cloud Console](https://console.groq.com/). |
| **Gmail App Password** | Authenticates your Gmail account securely for sending emails. | Generate from your Google Account under “Security → App Passwords”. |

> ⚠️ **Note:** You must use an **App Password**, not your regular Gmail password.

---

## 💾 Excel Data Format  

Ensure your Excel file (e.g., `a1.xlsx`) follows this structure 👇  

| **Column Name** | **Required?** | **Purpose** |
|------------------|---------------|--------------|
| `Date` | ✅ Yes | Application date — used for filtering jobs. |
| `Company Name` | ✅ Yes | Company applying to. |
| `Recruiter Name` | 🔸 Optional | Used for personalizing email greetings. |
| `Recruiter Email` | ⭐ Highly Recommended | Direct HR/recruiter contact. If empty, AI scrapes/guesses it. |
| `Job Description` | ✅ Yes | Full text used by LLM for resume customization. |

> 🧠 All column headers are automatically converted to **lowercase_snake_case** during processing.

---

## ▶️ Running the Application  

Launch the Streamlit app using:  

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

---

### 🖱️ Steps to Use  

1. Enter your **Name** and **Gmail Address**.  
2. Enter your **Gmail App Password**.  
3. Upload your **Base Resume File** (in `.md` or `.txt` format).  
4. Select the **Date** for which job entries exist in your Excel file.  
5. Click **“Submit Application”** — and let AI handle the rest! 🎯  

---

## 💡 Pro Tips  

- ✅ Keep your Excel file updated regularly with new job entries.  
- 💬 Add detailed job descriptions to get more accurate resume customization.  
- 🔁 Reuse the same setup — only the Excel file and date need updating for each batch.  

---

## 🧱 Tech Stack  

- **Frontend:** Streamlit  
- **Backend:** Python  
- **AI Engine:** Groq LLM API  
- **Mail Service:** Gmail SMTP (secure with App Passwords)  
- **File Handling:** Pandas + OpenPyXL  

---

## 🏁 Future Enhancements  

- Integration with LinkedIn Job Scraper  
- Multi-account Gmail rotation  
- Resume format selector (PDF/Markdown/HTML)  
- Application status tracking dashboard  

---

## 🧑‍💻 Author  

**Developed by:** [Prathamesh Vaidya](https://github.com/tksruser-pv)  
**Organization:** TKSR Global Consaltancy Services*  
