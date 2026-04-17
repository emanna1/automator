import time
import pandas as pd
from typing import List, Callable, Optional, Tuple


def _scrape_term(
    search_term: str,
    location: str,
    sites: List[str],
    hours_old: int,
    results_per_search: int,
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Returns (dataframe, error_string).
    error_string is None on success, a message string on failure.
    """
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
    jobs_list: deduplicated job dicts ready to insert into tracker.
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
                seen_urls.add(url)
                desc = str(row.get("description") or "")
                if desc.lower() == "nan":
                    desc = ""
                jobs.append({
                    "job_url":     url,
                    "title":       str(row.get("title") or "Unknown").strip(),
                    "company":     str(row.get("company") or "Unknown").strip(),
                    "location":    str(row.get("location") or "").strip(),
                    "date_posted": str(row.get("date_posted") or "").strip(),
                    "site":        str(row.get("site") or "").strip(),
                    "search_term": term,
                    "description": desc[:5000],
                })

        time.sleep(2)  # polite delay between search terms

    return jobs, errors
