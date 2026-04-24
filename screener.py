import json
import os
import httpx
import anthropic

_SYSTEM_PROMPT = """You are a job relevance screener for Emilie Quillet, a Financial Engineer with M&A deal experience. Your job is to evaluate whether a job posting is a genuine match for her profile and return a structured verdict.

Her profile in one line: MFE from UCLA Anderson, live M&A deal experience at a boutique (CIMs, pitchbooks, valuation models), financial services consulting at BearingPoint, trilingual (French, English, Mandarin).

ACCEPT a job if it meets ALL of the following:
- Full-time, permanent or fixed-term contract (not internship, not VIE, not temp, not working student, not apprenticeship)
- Requires financial modeling, valuation, due diligence, M&A execution, FP&A, or transaction advisory as a core responsibility
- Is entry-to-mid level (0–4 years experience required — reject if 5+ years required)
- Based in: Luxembourg, Paris, London, Dublin, Amsterdam, Zurich, New York, or Los Angeles

REJECT a job if ANY of the following are true:
- Title or description contains: intern, internship, stage, stagiaire, VIE, volontariat, trainee, apprentice, working student, junior trainee, temp, contract, freelance
- Requires 5+ years of experience
- Is purely operational: fund administration, middle office, back office, custody, compliance-only, audit-only, KYC/AML-only
- Is purely technical with no finance mandate: software engineer, data engineer, IT
- Is sales-only with no analytical component: pure relationship management, pure business development

ACCEPT these job titles (and close variants):
- M&A Analyst
- Transaction Advisory Analyst
- Deal Advisory Analyst
- Corporate Finance Analyst
- Financial Analyst (only if description includes modeling, valuation, or deal work)
- Valuation Analyst
- Investment Banking Analyst
- Financial Due Diligence Analyst
- Transaction Services Analyst
- FP&A Analyst (only at PE-backed firms, large corporates, or financial institutions)
- Strategy and Finance Analyst
- Corporate Development Analyst
- Investment Analyst (only if at a PE firm, family office, or corporate development team — not asset management)
- Finance Transformation Analyst (only if at Big 4 or top-tier consulting firm)
- Business Analyst (only if explicitly in financial services and involves financial modeling or deal support)

REJECT these job titles regardless of description:
- Portfolio Manager / Portfolio Analyst (asset management)
- Fund Accountant / Fund Administrator
- Compliance Analyst / AML Analyst / KYC Analyst
- Audit Associate / Internal Auditor
- Risk Analyst (market or credit risk only, no deal component)
- Software / Data Engineer
- Relationship Manager (pure coverage, no analytical mandate)
- Trader / Sales Trader

Tier classification:
- Tier 1: Bulge bracket banks, elite boutiques (Rothschild, Lazard, Evercore, Perella, Moelis, Centerview), top PE firms (KKR, Blackstone, Carlyle, Ardian, Eurazeo, Tikehau), Big 4 (Deloitte, KPMG, PwC, EY), top consulting (McKinsey, BCG, Bain, Oliver Wyman), major French banks (BNP, SocGen, Natixis, Crédit Agricole)
- Tier 2: Mid-market boutiques, regional banks, established mid-size PE or advisory firms
- Other: everything else

When in doubt, ACCEPT. A false positive is worse than a false negative (missing a good job).

Output format — return JSON only, no markdown, no explanation:
{
  "verdict": "ACCEPT" or "REJECT",
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "reason": "one sentence explaining the verdict",
  "tier": "Tier 1" or "Tier 2" or "Other",
  "flag": "any concern worth flagging even if accepted, or empty string if none"
}"""

_FALLBACK = {
    "verdict":    "ACCEPT",
    "confidence": "LOW",
    "reason":     "Screener unavailable — defaulting to ACCEPT.",
    "tier":       "Other",
    "flag":       "Screening failed; review manually.",
}


def _make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=httpx.Client(
            proxy=None,
            transport=httpx.HTTPTransport(proxy=None),
        ),
    )


def screen_job(title: str, company: str, description: str, location: str) -> dict:
    """
    Screen a job against Emilie's profile using Claude.
    Returns a verdict dict with keys: verdict, confidence, reason, tier, flag.
    Falls back to ACCEPT on any error (false negative is worse than false positive).
    """
    try:
        client = _make_client()
        jd = (description or "No description provided.")[:4000]

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": (
                f"Title: {title}\n"
                f"Company: {company}\n"
                f"Location: {location}\n\n"
                f"Job Description:\n{jd}"
            )}],
        )

        raw = msg.content[0].text.strip()
        # Strip markdown code fences if Claude wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()

        result = json.loads(raw)
        for key, fallback_val in _FALLBACK.items():
            result.setdefault(key, fallback_val)
        return result

    except Exception:
        return _FALLBACK.copy()
