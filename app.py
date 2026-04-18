"""
GongZuo — Emilie Quillet
Run: streamlit run app.py
"""

import html
import os
import re
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="GongZuo — Emilie",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from config import load_settings, save_settings
from tracker import (
    load_tracker, save_tracker,
    load_seen_jobs, save_seen_jobs,
    update_applied, update_files,
    COLUMNS,
)
from scraper import scrape_all
from cover_letter import generate_cover_letter, extract_ats_keywords
from cv_processor import inject_ats_keywords, save_cover_letter_docx, job_folder


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_filename(s: str, max_len: int = 30) -> str:
    return re.sub(r'[^\w\-]', '_', str(s))[:max_len]


def _is_applied(val) -> bool:
    return str(val).lower() in ("true", "1", "yes")


# ── core pipeline ─────────────────────────────────────────────────────────────

def _process_job(job: dict, settings: dict, status) -> dict:
    """Generate cover letter + modified CV for one job. Returns updated job dict."""
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown Company")
    description = job.get("description", "")
    location = job.get("location", settings.get("location", "Luxembourg"))
    date_str = str(job.get("date_posted", datetime.now().strftime("%Y-%m-%d")))[:10].replace("-", "")

    folder = job_folder(company, title, date_str)

    # Cover letter
    cover_text = ""
    cl_path = ""
    try:
        status.text(f"Processing — {title} @ {company}…")
        cover_text = generate_cover_letter(title, company, description, location)
        cl_path = str(folder / "cover_letter.docx")
        save_cover_letter_docx(cover_text, cl_path)
    except Exception as e:
        cover_text = f"[Error generating cover letter: {e}]"
        cl_path = ""

    # Modified CV
    cv_path_out = ""
    base_cv = settings.get("cv_path", "")
    if base_cv and Path(base_cv).exists():
        try:
            status.text(f"Optimising — {title} @ {company}…")
            keywords = extract_ats_keywords(title, description)
            cv_path_out = str(folder / "cv_modified.docx")
            inject_ats_keywords(base_cv, keywords, cv_path_out)
        except Exception as e:
            cv_path_out = ""
            st.warning(f"CV processing failed for {company}: {e}")

    return {**job, "cover_letter_text": cover_text,
            "cover_letter_path": cl_path, "cv_path": cv_path_out}


def run_pipeline(settings: dict, progress_bar, status) -> dict:
    """
    Runs full scrape + process pipeline.
    Returns a result dict: {found, new, errors, saved}
    so the caller can persist it in session_state.
    """
    seen = load_seen_jobs()
    df = load_tracker()

    status.text("Fetching data…")

    def _cb(pct: float, msg: str):
        progress_bar.progress(min(pct * 0.45, 0.45))
        status.text(msg)

    raw_jobs, scrape_errors = scrape_all(
        search_terms=settings["search_terms"],
        location=settings["location"],
        sites=settings["sites"],
        hours_old=settings["hours_old"],
        results_per_search=settings["results_per_search"],
        progress_callback=_cb,
    )
    progress_bar.progress(0.45)

    new_jobs = [j for j in raw_jobs if j["job_url"] not in seen]
    total_found = len(raw_jobs)
    total_new = len(new_jobs)

    saved = 0
    if new_jobs:
        new_rows = []
        for i, job in enumerate(new_jobs):
            progress_bar.progress(0.45 + (i / total_new) * 0.54)
            processed = _process_job(job, settings, status)
            processed["applied"] = "False"
            processed["scraped_at"] = datetime.now().isoformat()
            new_rows.append({col: str(processed.get(col, "")) for col in COLUMNS})
            seen.add(job["job_url"])

        new_df = pd.DataFrame(new_rows)
        df = pd.concat([new_df, df], ignore_index=True)
        save_tracker(df)
        save_seen_jobs(seen)
        saved = len(new_rows)

    progress_bar.progress(1.0)
    return {
        "found": total_found,
        "new": total_new,
        "saved": saved,
        "errors": scrape_errors,
    }


# ── sidebar: settings ─────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ Settings")
        settings = load_settings()

        with st.expander("Documents", expanded=True):
            cv_path = st.text_input(
                "Base CV path (.docx)",
                value=settings.get("cv_path", ""),
                help="Full path to CV Emilie Quillet v15.docx",
            )
            location = st.text_input("Location", value=settings.get("location", "Luxembourg"))
            hours_old = st.number_input(
                "Max age (hours)", min_value=1, max_value=168,
                value=int(settings.get("hours_old", 24))
            )
            results_n = st.number_input(
                "Results per search term", min_value=1, max_value=50,
                value=int(settings.get("results_per_search", 15))
            )
            sites_options = ["linkedin", "indeed", "glassdoor"]
            sites_sel = st.multiselect(
                "Sources",
                sites_options,
                default=[s for s in settings.get("sites", sites_options) if s in sites_options],
            )

        with st.expander("Keywords", expanded=False):
            terms_text = st.text_area(
                "One per line",
                value="\n".join(settings.get("search_terms", [])),
                height=240,
            )

        if st.button("💾 Save Settings", use_container_width=True, type="primary"):
            new_settings = {
                "cv_path": cv_path.strip(),
                "location": location.strip(),
                "hours_old": int(hours_old),
                "results_per_search": int(results_n),
                "sites": sites_sel,
                "search_terms": [t.strip() for t in terms_text.splitlines() if t.strip()],
            }
            save_settings(new_settings)
            st.success("Saved.")

        st.divider()
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            st.success("API key: set ✓")
        else:
            st.error("ANTHROPIC_API_KEY not set in environment")

        base_cv = settings.get("cv_path", "")
        if base_cv and Path(base_cv).exists():
            st.success("CV file: found ✓")
        else:
            st.warning("CV file not found — check path above")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    col_btn, col_info = st.columns([2, 3])
    with col_btn:
        run_pressed = st.button("▶  Refresh", type="primary", use_container_width=True)

    if run_pressed:
        settings = load_settings()
        if not settings.get("search_terms"):
            st.error("Add search terms in Settings first.")
        elif not settings.get("sites"):
            st.error("Select at least one job board in Settings.")
        else:
            prog = st.progress(0)
            status = st.empty()
            try:
                result = run_pipeline(settings, prog, status)
                status.empty()
                prog.empty()
                st.session_state["last_scrape"] = result
                st.rerun()
            except Exception:
                st.error("Scraper crashed — see details below.")
                st.code(traceback.format_exc())

    # ── Persistent scrape result banner (survives the rerun) ─────────────────
    if "last_scrape" in st.session_state:
        r = st.session_state["last_scrape"]
        found, new, saved = r["found"], r["new"], r["saved"]
        errors = r.get("errors", [])

        if saved > 0:
            st.success(
                f"Last refresh — **{found}** entries found, "
                f"**{new}** were new, **{saved}** added."
            )
        elif found > 0 and new == 0:
            st.info(
                f"Last refresh — **{found}** entries found, all already seen. "
                "No new entries added."
            )
        elif found == 0 and not errors:
            st.warning(
                "Last refresh returned 0 results. "
                "Try increasing **Max age (hours)** or check your VPN/network."
            )
        else:
            st.warning(f"Last refresh — **{found}** entries found, **{saved}** saved.")

        if errors:
            with st.expander(f"⚠️ {len(errors)} error(s) — click to expand"):
                for e in errors:
                    st.code(e)

    # ── Load data ─────────────────────────────────────────────────────────────
    df = load_tracker()

    if df.empty:
        st.info("No entries yet. Click **Refresh** to start.")
        return

    # ── Stats ─────────────────────────────────────────────────────────────────
    total = len(df)
    applied = df["applied"].apply(_is_applied).sum()
    today = datetime.now().strftime("%Y-%m-%d")
    new_today = df["scraped_at"].str[:10].eq(today).sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Total", total)
    m2.metric("Sent", int(applied))
    m3.metric("New today", int(new_today))

    st.divider()

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        f_status = st.selectbox("Status", ["All", "Pending", "Sent"])
    with fc2:
        sites_in_data = sorted(df["site"].replace("", pd.NA).dropna().unique().tolist())
        f_site = st.selectbox("Source", ["All"] + sites_in_data)
    with fc3:
        f_search = st.text_input("Search title / company", "")

    view = df.copy().reset_index(drop=True)
    if f_status == "Sent":
        view = view[view["applied"].apply(_is_applied)]
    elif f_status == "Pending":
        view = view[~view["applied"].apply(_is_applied)]
    if f_site != "All":
        view = view[view["site"] == f_site]
    if f_search:
        mask = (
            view["title"].str.contains(f_search, case=False, na=False) |
            view["company"].str.contains(f_search, case=False, na=False)
        )
        view = view[mask]
    view = view.reset_index(drop=True)

    # ── Jobs table ────────────────────────────────────────────────────────────
    table_cols = ["title", "company", "location", "date_posted", "site", "applied", "scraped_at"]
    table_df = view[[c for c in table_cols if c in view.columns]].copy()
    table_df["applied"] = table_df["applied"].apply(_is_applied)
    table_df["scraped_at"] = (
        pd.to_datetime(table_df["scraped_at"], errors="coerce")
        .dt.strftime("%m-%d %H:%M")
        .fillna(table_df["scraped_at"].str[:16])
    )

    st.subheader(f"Entries ({len(table_df)})")
    event = st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "title":       st.column_config.TextColumn("Title", width="medium"),
            "company":     st.column_config.TextColumn("Company", width="medium"),
            "location":    st.column_config.TextColumn("Location", width="small"),
            "date_posted": st.column_config.TextColumn("Posted", width="small"),
            "site":        st.column_config.TextColumn("Source", width="small"),
            "applied":     st.column_config.CheckboxColumn("Sent", width="small"),
            "scraped_at":  st.column_config.TextColumn("Scraped", width="small"),
        },
    )

    # ── Detail panel ─────────────────────────────────────────────────────────
    if not (event.selection and event.selection.rows):
        st.caption("Click a row to see details.")
        return

    idx = event.selection.rows[0]
    if idx >= len(view):
        return
    job = view.iloc[idx]

    st.divider()
    st.subheader(f"{job['title']}  ·  {job['company']}")

    left, right = st.columns([3, 1])

    with right:
        # Applied toggle
        cur_applied = _is_applied(job.get("applied", "False"))
        new_applied = st.checkbox("✅ Applied", value=cur_applied, key=f"chk_{job['job_url']}")
        if new_applied != cur_applied:
            update_applied(job["job_url"], new_applied)
            st.rerun()

        st.write("")

        # Job URL
        url = job.get("job_url", "")
        if url:
            st.link_button("🔗 View", url)

        # Download modified CV
        cv_p = str(job.get("cv_path", ""))
        if cv_p and Path(cv_p).exists():
            with open(cv_p, "rb") as f:
                st.download_button(
                    "📄 Download CV",
                    data=f.read(),
                    file_name=f"CV_{_safe_filename(job['company'])}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        else:
            if not load_settings().get("cv_path"):
                st.caption("Set CV path in Settings to enable ATS injection.")
            else:
                st.caption("Modified CV not generated yet.")

        # Download cover letter docx
        cl_p = str(job.get("cover_letter_path", ""))
        if cl_p and Path(cl_p).exists():
            with open(cl_p, "rb") as f:
                st.download_button(
                    "📝 Download letter",
                    data=f.read(),
                    file_name=f"CoverLetter_{_safe_filename(job['company'])}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

        st.divider()
        st.caption(f"Source: {job.get('site', '—')}")
        st.caption(f"Posted: {job.get('date_posted', '—')}")
        st.caption(f"Scraped: {str(job.get('scraped_at', ''))[:16]}")
        st.caption(f"Search term: {job.get('search_term', '—')}")

    with left:
        cover_text = str(job.get("cover_letter_text", "")).strip()

        if cover_text and not cover_text.startswith("[Error"):
            st.subheader("Letter")
            st.markdown(
                f"""<div style="
                    background:#f8f9fb;border-radius:8px;padding:20px 24px;
                    font-family:Georgia,serif;font-size:14px;line-height:1.7;
                    white-space:pre-wrap;border:1px solid #e0e4ea;">
{html.escape(cover_text)}
                </div>""",
                unsafe_allow_html=True,
            )
        elif cover_text.startswith("[Error"):
            st.warning(cover_text)
            _regen_button(job, left)
        else:
            st.info("No letter generated yet.")
            _regen_button(job, left)

        # Show JD excerpt
        desc = str(job.get("description", "")).strip()
        if desc and desc != "nan":
            with st.expander("Details", expanded=False):
                st.text(desc[:3000])


def _regen_button(job, col):
    if st.button("🔄 Generate letter", key=f"regen_{job['job_url']}"):
        settings = load_settings()
        with st.spinner("Generating…"):
            try:
                text = generate_cover_letter(
                    job["title"], job["company"],
                    job.get("description", ""),
                    job.get("location", "Luxembourg"),
                )
                date_str = str(job.get("date_posted", ""))[:10].replace("-", "")
                folder = job_folder(job["company"], job["title"], date_str)
                cl_path = str(folder / "cover_letter.docx")
                save_cover_letter_docx(text, cl_path)
                update_files(job["job_url"], cover_letter_text=text, cover_letter_path=cl_path)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")


if __name__ == "__main__":
    main()
