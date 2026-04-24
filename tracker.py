import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Set

_BASE = Path(__file__).parent
DATA_DIR = _BASE / "data"
DATA_DIR.mkdir(exist_ok=True)

SEEN_JOBS_FILE = DATA_DIR / "seen_jobs.json"
TRACKER_CSV = DATA_DIR / "jobs_tracker.csv"

COLUMNS = [
    "job_url", "title", "company", "location", "date_posted",
    "site", "search_term", "description",
    "cover_letter_text", "cover_letter_path", "cv_path",
    "applied", "scraped_at",
    "ai_verdict", "ai_confidence", "ai_reason", "ai_tier", "ai_flag",
]


def load_seen_jobs() -> Set[str]:
    if SEEN_JOBS_FILE.exists():
        return set(json.loads(SEEN_JOBS_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen_jobs(seen: Set[str]):
    SEEN_JOBS_FILE.write_text(
        json.dumps(list(seen)), encoding="utf-8"
    )


def load_tracker() -> pd.DataFrame:
    if TRACKER_CSV.exists():
        df = pd.read_csv(TRACKER_CSV, dtype=str).fillna("")
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)


def save_tracker(df: pd.DataFrame):
    df[COLUMNS].to_csv(TRACKER_CSV, index=False, encoding="utf-8")


def append_job(row: dict) -> pd.DataFrame:
    df = load_tracker()
    new_row = {col: str(row.get(col, "")) for col in COLUMNS}
    new_row["applied"] = "False"
    new_row["scraped_at"] = datetime.now().isoformat()
    df = pd.concat([pd.DataFrame([new_row]), df], ignore_index=True)
    save_tracker(df)
    return df


def update_applied(job_url: str, applied: bool):
    df = load_tracker()
    df.loc[df["job_url"] == job_url, "applied"] = str(applied)
    save_tracker(df)


def update_files(job_url: str, cover_letter_text: str = None,
                 cover_letter_path: str = None, cv_path: str = None):
    df = load_tracker()
    mask = df["job_url"] == job_url
    if cover_letter_text is not None:
        df.loc[mask, "cover_letter_text"] = cover_letter_text
    if cover_letter_path is not None:
        df.loc[mask, "cover_letter_path"] = cover_letter_path
    if cv_path is not None:
        df.loc[mask, "cv_path"] = cv_path
    save_tracker(df)
