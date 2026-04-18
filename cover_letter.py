import os
import anthropic

EMILIE_PROFILE = """
CURRENT SITUATION:
- Business Analyst at BearingPoint Luxembourg (April 2026–present)
  Banking & Capital Markets consulting: financial transformation, process optimisation,
  client presentations, digital transformation projects in the financial sector.
- French national, based in Luxembourg, working legally.
- Languages: English (native), French (native), Chinese (fluent HSK4).

EDUCATION:
- Master of Financial Engineering, UCLA Anderson School of Management — GPA 3.44 | Dec 2025
- BSc Business Administration Finance, NC State University — GPA 4.00 Summa Cum Laude | May 2023
- BBA Global Management Finance, SKEMA Business School — GPA 3.87 Summa Cum Laude | May 2023

EXPERIENCE (most recent first):
1. BearingPoint Luxembourg — Business Analyst (April 2026–present)
   Client-facing project work in Banking & Capital Markets. Wealth management, private banking,
   financial transformation. Process optimisation, dashboards, client presentations.

2. Quint Capital Corporation, New York — Financial Analyst Intern (Jan–Mar 2026)
   M&A boutique. Built financial models for forecasting, scenario and variance analysis.
   Industry and macro analysis for valuation assumptions. Prepared teasers, CIMs, pitchbooks.
   Contributed to live M&A transactions: financial analysis and execution support.

3. Lido Advisors, Los Angeles/San Diego — Wealth Management Intern (Jun–Aug 2025)
   $30B AUM firm. Built ML-driven portfolio reweighting models with ESG tilts.
   Python-based ESG framework for S&P 500 sector allocation. Presented to HNW clients.

4. Visionaries 777, Hong Kong — Financial Analyst Intern (Aug–Dec 2023)
   AR/VR tech startup (clients: Lego, Cartier). Built 3-year financial forecast and valuation model.
   Automated financial models for investor reporting. CEO pitch decks for stakeholder presentations.

5. BNP Paribas, Nice — Wealth Management Intern (May–Jul 2022)
   Weekly market reports. DCF-based valuations and financial analysis for SMEs.

TECHNICAL SKILLS: Python, SQL, MATLAB, R, Tableau, SAS, Excel (advanced), Bloomberg, PowerPoint.

PERSONAL: Competitive swimmer at national level 2011–2023 (French National Championships, FFN Golden
Tour, CCS Nationals). Instilled discipline and performance under pressure.
"""

COVER_LETTER_EXAMPLES = """
EXAMPLE 1 — SocGen VIE M&A:
---
Dear Hiring Manager,
I'm drawn to this VIE M&A position within Société Générale's Client Advisory Team because it combines
two things I've pursued deliberately: cross-border deal execution and deep client relationship work
within a French institution I know well.

My financial modelling foundation directly supports this mandate. At Quint Capital in New York, I built
DCF, LBO, and comparables models for live M&A transactions and prepared CIMs and pitchbooks under
deal deadlines. At UCLA Anderson, I completed coursework in derivative pricing and capital structure
optimisation. At Visionaries 777, I created automated financial models and CEO pitch decks for
stakeholder presentations — translating complex scenarios into materials that drove decisions.

What distinguishes my candidacy is the combination of three things: the quant rigour from my MFE, the
live deal exposure from Quint Capital, and the cultural fluency that comes from being natively
bilingual in French and English with fluent Mandarin. I've worked across New York, Hong Kong, Los
Angeles, and Luxembourg — I know how to adapt quickly.
Sincerely, Emilie Quillet
---

EXAMPLE 2 — Keensight Capital PE:
---
Dear Hiring Manager,
Keensight's focus on high-growth B2B Healthcare and Technology companies resonates with the way I
approach analysis — from the bottom up, with a view on how a business model scales.

At Quint Capital, I supported live M&A transactions with financial modelling, scenario analysis, and
investor-facing materials. At Lido Advisors, I built ML-driven portfolio optimisation models for a
$30B AUM firm, developing a Python-based ESG framework for sector allocation. At UCLA Anderson, my
coursework in financial engineering and data analysis sharpened my ability to stress-test assumptions
and model non-linear outcomes.

I bring the analytical infrastructure PE firms require — Python, Excel, Bloomberg, valuation
frameworks — plus the cross-border fluency (French, English, Mandarin) that accelerates due diligence
on international targets.
Sincerely, Emilie Quillet
---

EXAMPLE 3 — Crédit Agricole Coverage:
---
Dear Hiring Manager,
This Coverage Analyst role appeals to me precisely because it sits at the nexus of relationship banking
and deal origination — where understanding a client's strategic agenda matters as much as the
modelling.

At BNP Paribas in Nice, I worked directly with relationship bankers, preparing market reports and
DCF-based financial analyses for client advisory. At Quint Capital, I contributed to M&A mandates
from origination through execution, producing CIMs, teasers, and pitchbooks. My experience on both
sides — the French banking relationship model and the boutique advisory model — gives me an unusual
vantage point for a coverage role.

Being natively French and bilingual naturally helps in a French institution. I understand the culture,
the formality, and the standards for client communication.
Sincerely, Emilie Quillet
---
"""

_TONE_RULES = [
    (["rothschild", "lazard", "perella weinberg", "evercore", "centerview", "moelis", "guggenheim"],
     "TONE: Elite boutique. Formal, precise, understated. Let credentials speak. No enthusiasm-signalling. "
     "Lead with intellectual substance. Every sentence earns its place."),

    (["eurazeo", "tikehau", "ardian", "kkr", "carlyle", "blackstone", "apollo", "warburg", "tpg", "bain capital"],
     "TONE: Private equity. Sharp and investor-minded. Lead with quantitative instincts. "
     "Show you think about returns, deal dynamics, and analytical rigour — not just process."),

    (["deloitte", "kpmg", "pwc", "ey", "ernst", "bearingpoint", "mckinsey", "bcg", "bain", "oliver wyman",
      "accenture", "capgemini"],
     "TONE: Consulting / Big 4. Professional and warm. Emphasise team collaboration, client communication, "
     "and structured thinking. Analytical rigour paired with clear communication is the key message."),

    (["bnp", "société générale", "societe generale", "soc gen", "natixis", "crédit agricole",
      "credit agricole", "cacib", "bred", "cic"],
     "TONE: French bank. Collegial and professional. Emphasise native French fluency and understanding "
     "of French banking culture. Cross-border coordination is a strong card."),

    (["jp morgan", "jpmorgan", "goldman sachs", "goldman", "morgan stanley", "bank of america",
      "merrill lynch", "citi", "citibank", "barclays", "deutsche bank", "ubs", "hsbc"],
     "TONE: Bulge bracket. Confident and high-energy. Show intellectual curiosity, market awareness, "
     "and ambition. These firms want drive paired with analytical foundation."),
]


def _detect_tone(company: str) -> str:
    c = company.lower()
    for keywords, tone in _TONE_RULES:
        if any(k in c for k in keywords):
            return tone
    return ("TONE: Direct and confident. Match the register of the JD. "
            "Lead with something specific to this company and role.")


def generate_cover_letter(title: str, company: str, description: str, location: str = "Luxembourg") -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    tone = _detect_tone(company)
    jd = description[:3500] if description else "No description provided."

    prompt = f"""You are writing a cover letter for Emilie Quillet. Study her profile and voice carefully.

═══════════════════════
EMILIE'S PROFILE
═══════════════════════
{EMILIE_PROFILE}

═══════════════════════
HER VOICE — real examples she approved:
═══════════════════════
{COVER_LETTER_EXAMPLES}

═══════════════════════
THE JOB
═══════════════════════
Title: {title}
Company: {company}
Location: {location}
Job Description:
{jd}

═══════════════════════
TONE INSTRUCTION
═══════════════════════
{tone}

═══════════════════════
STRICT RULES
═══════════════════════
STRUCTURE (3 short paragraphs, no bullet points inside the letter):
1. Opening: What specifically draws her to THIS role at THIS company. Reference something real from
   the JD — a mandate, a team structure, a product. Never generic. Never "I am writing to apply."
2. Middle: Connect 2 of her most relevant experiences to the role's key requirements. Name the
   company, the output, the skill. No vague claims.
3. Close: What she uniquely brings (multilingual, cross-border, quant + client-facing). Confident
   sign-off — not "I hope to hear from you."

NEVER write:
- "I am writing to express my interest" or any variation
- "I am passionate about finance" — too generic
- "I would be a great fit" — let the evidence speak
- "Please find attached my CV" or "I look forward to hearing from you"
- Any sentence that could appear unchanged in another person's letter
- More than 280 words total

ALWAYS:
- Open with "Dear Hiring Manager,"
- Close with "Sincerely, Emilie Quillet"
- British English spelling

Return only the cover letter text. No preamble, no explanation."""

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def extract_ats_keywords(title: str, description: str) -> list:
    if not description or description == "nan":
        return []
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    jd = description[:3500]

    prompt = f"""Extract the most important ATS keywords from this job description.
Focus on: technical skills, tools, financial methods, role-specific terminology, qualifications.
Return ONLY a comma-separated list. No explanation, no numbering. Max 40 keywords.

Title: {title}
Description:
{jd}"""

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    return [k.strip() for k in raw.split(",") if k.strip()]
