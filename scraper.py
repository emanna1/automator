import re
import time
import pandas as pd
from typing import List, Callable, Optional, Tuple


# ── Exclusion list — titles containing any of these are dropped ───────────────
# Edit this list to adjust what gets filtered out.

EXCLUDE_TITLE_KEYWORDS = [
    "intern",
    "internship",
    "stage",
    "stagiaire",
    "trainee",
    "apprentice",
    "apprenti",
    "student",
    "étudiant",
    "working student",
    "praktikum",
    "vie",
    "volontariat",
    "summer analyst",
    "junior trainee",
    "graduate trainee",
    "master thesis",
]

# Pre-compiled as word-boundary patterns so "intern" doesn't match "international"
_EXCLUDE_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in EXCLUDE_TITLE_KEYWORDS
]


# ── Preferred company whitelist — matched as case-insensitive substrings ──────
# Edit this list to add or remove Tier 1 firms.

PREFERRED_COMPANIES = [
    # US banks with Luxembourg offices
    "j.p. morgan", "jpmorgan", "jp morgan",
    "bank of america", "bofa", "merrill lynch",
    "citi", "citigroup", "citibank",
    "goldman sachs",
    "morgan stanley",
    "u.s. bank", "us bank",
    "state street",
    "northern trust",
    "brown brothers harriman", "bbh",
    "bny mellon", "bank of new york mellon",
    "fidelity",
    "wells fargo",
    "jefferies",
    # Elite boutiques & advisory
    "lazard", "rothschild", "evercore", "centerview", "perella weinberg",
    "moelis", "pjt", "guggenheim", "houlihan lokey", "greenhill",
    "lincoln international", "william blair", "raymond james",
    # European banks with international reach
    "bnp paribas", "bgl bnp", "société générale", "societe generale",
    "crédit agricole", "credit agricole", "cacib", "natixis",
    "deutsche bank", "ubs", "credit suisse", "barclays", "hsbc",
    "ing", "bbva", "santander", "nordea", "kbc", "intesa sanpaolo",
    "dz bank", "commerzbank", "crédit mutuel", "credit mutuel",
    # Luxembourg major institutions
    "european investment bank", "eib", "esm", "european stability mechanism",
    "banque internationale à luxembourg", "bil", "banque de luxembourg",
    "quintet", "spuerkeess", "bcee", "bgl",
    # PE / asset managers
    "blackstone", "kkr", "carlyle", "apollo", "brookfield", "ardian",
    "tikehau", "eurazeo", "cinven", "eqt", "cvc", "permira",
    "bridgepoint", "advent", "bain capital",
    "blackrock", "pictet", "lombard odier", "schroders",
    "alter domus", "iq-eq", "pimco", "vanguard", "carmignac", "amundi",
    # Big 4 / consulting
    "deloitte", "kpmg", "pwc", "ey", "ernst & young",
    "mckinsey", "bcg", "bain & company", "bain and company",
    "bearingpoint", "oliver wyman", "roland berger", "accenture",
    "mazars", "bdo",
]


def _is_excluded(title: str) -> bool:
    """Return True if the title matches any exclusion keyword (word-boundary match)."""
    return any(p.search(title) for p in _EXCLUDE_PATTERNS)


def get_tier(company: str) -> str:
    """Return '★ Tier 1' if company matches the preferred list, else ''."""
    c = company.lower()
    return "★ Tier 1" if any(p in c for p in PREFERRED_COMPANIES) else ""


# ── Scraping ──────────────────────────────────────────────────────────────────

def _scrape_term(
    search_term: str,
    location: str,
    sites: List[str],
    hours_old: int,
    results_per_search: int,
) -> Tuple[pd.DataFrame, Optional[str]]:
    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(
            site_name=sites,
            search_term=search_term,
            location=location,
            results_wanted=results_per_search,
            hours_old=hours_old,
            country_indeed="Luxembourg",
        )
        if df is not None and not df.empty:
            df["search_term"] = search_term
            return df, None
        return pd.DataFrame(), None
    except Exception as e:
        return pd.DataFrame(), f"'{search_term}': {e}"


def scrape_all(
    search_terms: List[str],
    location: str,
    sites: List[str],
    hours_old: int,
    results_per_search: int,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Tuple[List[dict], List[str]]:
    """
    Returns (jobs_list, errors_list).
    jobs_list: deduplicated, exclusion-filtered job dicts ready for the tracker.
    errors_list: human-readable error strings for display in the UI.
    """
    seen_urls: set = set()
    jobs: List[dict] = []
    errors: List[str] = []

    for i, term in enumerate(search_terms):
        if progress_callback:
            progress_callback(i / len(search_terms), f"Scraping: {term}")

        df, err = _scrape_term(term, location, sites, hours_old, results_per_search)

        if err:
            errors.append(err)
        else:
            for _, row in df.iterrows():
                url = str(row.get("job_url") or "").strip()
                if not url or url in seen_urls:
                    continue
                title = str(row.get("title") or "Unknown").strip()
                if _is_excluded(title):
                    continue
                seen_urls.add(url)
                desc = str(row.get("description") or "")
                if desc.lower() == "nan":
                    desc = ""
                jobs.append({
                    "job_url":     url,
                    "title":       title,
                    "company":     str(row.get("company") or "Unknown").strip(),
                    "location":    str(row.get("location") or "").strip(),
                    "date_posted": str(row.get("date_posted") or "").strip(),
                    "site":        str(row.get("site") or "").strip(),
                    "search_term": term,
                    "description": desc[:5000],
                })

        time.sleep(2)  # polite delay between search terms

    return jobs, errors
