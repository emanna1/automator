import json
from pathlib import Path

_BASE = Path(__file__).parent

SETTINGS_FILE = _BASE / "settings.json"

DEFAULT_SETTINGS = {
    "search_terms": [
        "M&A Analyst",
        "Mergers Acquisitions Analyst",
        "Transaction Advisory",
        "Transaction Services Analyst",
        "Corporate Finance Analyst",
        "Financial Analyst Luxembourg",
        "Valuation Analyst",
        "Investment Analyst",
        "FP&A Analyst",
        "Deal Advisory Analyst",
        "Due Diligence Analyst",
        "Business Analyst Financial Services",
        "Finance Consultant Luxembourg",
    ],
    "location": "Luxembourg",
    "sites": ["linkedin", "indeed"],
    "hours_old": 24,
    "results_per_search": 5,
    "cv_path": str(_BASE / "CV Emilie Quillet v15.docx"),
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
