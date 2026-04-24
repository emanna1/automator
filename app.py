"""
GongZuo DongXi — Emilie Quillet
Run: streamlit run app.py
"""

import html
import hashlib
import os
import re
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="GongZuo DongXi",
    page_icon="🗂️",
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
from scraper import scrape_all, get_tier
from screener import screen_job
from cover_letter import generate_cover_letter, extract_ats_keywords
from cv_processor import (
    inject_ats_keywords, save_cover_letter_docx, job_folder,
    check_base_cv, copy_base_cv_to_temp, url_hash, MARKER,
)


# ── site display mapping ──────────────────────────────────────────────────────

_SITE_DISPLAY = {"linkedin": "Source A", "indeed": "Source B", "glassdoor": "Source C"}
_SITE_REVERSE = {v: k for k, v in _SITE_DISPLAY.items()}


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_filename(s: str, max_len: int = 30) -> str:
    return re.sub(r'[^\w\-]', '_', str(s))[:max_len]


def _is_applied(val) -> bool:
    return str(val).lower() in ("true", "1", "yes")


# ── core pipeline ─────────────────────────────────────────────────────────────

def _process_job(job: dict, settings: dict, status, temp_cv_path: str = "") -> dict:
    title       = job.get("title", "Unknown Role")
    company     = job.get("company", "Unknown Company")
    description = job.get("description", "")
    location    = job.get("location", settings.get("location", "Luxembourg"))
    job_url     = job.get("job_url", "")
    date_str    = str(job.get("date_posted", datetime.now().strftime("%Y-%m-%d")))[:10].replace("-", "")
    uhash       = url_hash(job_url) if job_url else ""

    folder = job_folder(company, title, date_str, uhash)

    cover_text = ""
    cl_path = ""
    try:
        status.text(f"Processing — {title} @ {company}…")
        cover_text = generate_cover_letter(title, company, description, location)
        cl_path = str(folder / "cover_letter.docx")
        save_cover_letter_docx(cover_text, cl_path)
    except Exception as e:
        cover_text = f"[Error generating document: {type(e).__name__}: {e}]"
        cl_path = ""

    cv_path_out = ""
    base_cv = temp_cv_path or settings.get("cv_path", "")
    if base_cv and Path(base_cv).exists():
        try:
            status.text(f"Optimising — {title} @ {company}…")
            keywords = extract_ats_keywords(title, description)
            cv_path_out = str(folder / "cv_modified.docx")
            diag = inject_ats_keywords(base_cv, keywords, cv_path_out)
            # Store diagnostics in session state keyed by job URL
            if "cv_diagnostics" not in st.session_state:
                st.session_state["cv_diagnostics"] = {}
            st.session_state["cv_diagnostics"][job_url] = diag
        except Exception as e:
            cv_path_out = ""
            st.warning(f"File processing failed for {company}: {type(e).__name__}: {e}")

    return {**job, "cover_letter_text": cover_text,
            "cover_letter_path": cl_path, "cv_path": cv_path_out}


def run_pipeline(settings: dict, progress_bar, status) -> dict:
    seen = load_seen_jobs()
    df = load_tracker()

    # Copy base CV to local temp once per run to avoid OneDrive locking
    base_cv = settings.get("cv_path", "")
    temp_cv = ""
    if base_cv and Path(base_cv).exists():
        try:
            temp_cv = copy_base_cv_to_temp(base_cv)
        except Exception as e:
            st.warning(f"Could not copy base CV to temp ({type(e).__name__}): {e}")

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

            # Screen the job before expensive processing
            status.text(f"Screening — {job['title']} @ {job['company']}…")
            screen = screen_job(
                job["title"], job["company"],
                job.get("description", ""), job.get("location", ""),
            )
            job["ai_verdict"]    = screen.get("verdict",    "ACCEPT")
            job["ai_confidence"] = screen.get("confidence", "LOW")
            job["ai_reason"]     = screen.get("reason",     "")
            job["ai_tier"]       = screen.get("tier",       "Other")
            job["ai_flag"]       = screen.get("flag",       "")

            if job["ai_verdict"] == "REJECT":
                processed = {
                    **job,
                    "cover_letter_text": "", "cover_letter_path": "", "cv_path": "",
                }
            else:
                processed = _process_job(job, settings, status, temp_cv_path=temp_cv)

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


# ── sidebar: options ──────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ Options")
        settings = load_settings()

        with st.expander("Config", expanded=True):
            cv_path = st.text_input(
                "Base file path",
                value=settings.get("cv_path", ""),
                help="Full path to base .docx file",
            )
            location = st.text_input("Region", value=settings.get("location", "Luxembourg"))
            hours_old = st.number_input(
                "Range (hrs)", min_value=1, max_value=168,
                value=int(settings.get("hours_old", 24))
            )
            results_n = st.number_input(
                "Limit", min_value=1, max_value=50,
                value=int(settings.get("results_per_search", 15))
            )
            sites_options = ["linkedin", "indeed", "glassdoor"]
            sites_sel_display = st.multiselect(
                "Sources",
                [_SITE_DISPLAY[s] for s in sites_options],
                default=[_SITE_DISPLAY[s] for s in settings.get("sites", sites_options) if s in _SITE_DISPLAY],
            )
            sites_sel = [_SITE_REVERSE[d] for d in sites_sel_display]

        with st.expander("Filters", expanded=False):
            terms_text = st.text_area(
                "One per line",
                value="\n".join(settings.get("search_terms", [])),
                height=240,
            )

        if st.button("💾 Save", use_container_width=True, type="primary"):
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
        if base_cv:
            cv_check = check_base_cv(base_cv)
            if not cv_check["exists"]:
                st.warning("Base file not found — check path above")
            elif not cv_check["readable"]:
                st.error(f"Base file unreadable: {cv_check['error']}")
            elif not cv_check["has_marker"]:
                st.success("Base file: found ✓")
                st.warning(
                    f"Marker missing — open the base CV in Word and replace "
                    f"the placeholder line text with exactly: `{MARKER}`"
                )
            else:
                st.success("Base file: found ✓  |  marker: found ✓")
        else:
            st.warning("Base file not found — check path above")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()
    st.header("🗂️ GongZuo DongXi")

    col_btn, col_info = st.columns([2, 3])
    with col_btn:
        run_pressed = st.button("▶  Sync", type="primary", use_container_width=True)

    if run_pressed:
        settings = load_settings()
        if not settings.get("search_terms"):
            st.error("Configure filters in Options first.")
        elif not settings.get("sites"):
            st.error("Select at least one source in Options.")
        else:
            prog = st.progress(0)
            status = st.empty()
            try:
                result = run_pipeline(settings, prog, status)
                status.empty()
                prog.empty()
                st.session_state["last_sync"] = result
                st.rerun()
            except Exception:
                st.error("Sync failed — see details below.")
                st.code(traceback.format_exc())

    # ── Persistent result banner ──────────────────────────────────────────────
    if "last_sync" in st.session_state:
        r = st.session_state["last_sync"]
        found, new, saved = r["found"], r["new"], r["saved"]
        errors = r.get("errors", [])

        if saved > 0:
            st.success(
                f"Last sync — **{found}** entries retrieved, "
                f"**{new}** were new, **{saved}** added."
            )
        elif found > 0 and new == 0:
            st.info(
                f"Last sync — **{found}** entries retrieved, all already seen. "
                "No new entries added."
            )
        elif found == 0 and not errors:
            st.warning(
                "Last sync returned 0 results. "
                "Try increasing **Range (hrs)** or check your VPN/network."
            )
        else:
            st.warning(f"Last sync — **{found}** entries retrieved, **{saved}** saved.")

        if errors:
            with st.expander(f"⚠️ {len(errors)} error(s) — click to expand"):
                for e in errors:
                    st.code(e)

    # ── Load data ─────────────────────────────────────────────────────────────
    df = load_tracker()

    if df.empty:
        st.info("No entries. Click **Sync** to begin.")
        return

    # ── Stats ─────────────────────────────────────────────────────────────────
    total = len(df)
    processed = df["applied"].apply(_is_applied).sum()
    today = datetime.now().strftime("%Y-%m-%d")
    new_today = df["scraped_at"].str[:10].eq(today).sum()

    accepted = (df["ai_verdict"] == "ACCEPT").sum()
    rejected = (df["ai_verdict"] == "REJECT").sum()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", total)
    m2.metric("Matched", int(accepted))
    m3.metric("Filtered", int(rejected))
    m4.metric("Processed", int(processed))

    st.divider()

    # ── Filters ───────────────────────────────────────────────────────────────
    fr1c1, fr1c2, fr1c3 = st.columns(3)
    with fr1c1:
        f_verdict = st.selectbox("Match", ["Accepted only", "All", "Rejected only"])
    with fr1c2:
        f_tier = st.selectbox("Tier", ["All", "Tier 1 only", "Other only"])
    with fr1c3:
        f_status = st.selectbox("Status", ["All", "Pending", "Processed"])

    fr2c1, fr2c2, fr2c3 = st.columns(3)
    with fr2c1:
        sites_in_data = sorted(df["site"].replace("", pd.NA).dropna().unique().tolist())
        sites_display_opts = [_SITE_DISPLAY.get(s, s) for s in sites_in_data]
        f_site_display = st.selectbox("Origin", ["All"] + sites_display_opts)
        f_site = _SITE_REVERSE.get(f_site_display, f_site_display)
    with fr2c2:
        f_search = st.text_input("Filter", "")
    with fr2c3:
        pass  # reserved

    view = df.copy().reset_index(drop=True)
    view["tier"] = view["company"].apply(get_tier)

    # Verdict filter (default: accepted only)
    if f_verdict == "Accepted only":
        view = view[view["ai_verdict"].isin(["ACCEPT", ""])]
    elif f_verdict == "Rejected only":
        view = view[view["ai_verdict"] == "REJECT"]

    if f_status == "Processed":
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
    if f_tier == "Tier 1 only":
        view = view[view["tier"] == "★ Tier 1"]
    elif f_tier == "Other only":
        view = view[view["tier"] == ""]
    view = view.reset_index(drop=True)

    # ── Table ─────────────────────────────────────────────────────────────────
    table_cols = ["ai_verdict", "tier", "title", "company", "location",
                  "date_posted", "site", "applied", "scraped_at"]
    table_df = view[[c for c in table_cols if c in view.columns]].copy()
    table_df["applied"] = table_df["applied"].apply(_is_applied)
    table_df["scraped_at"] = (
        pd.to_datetime(table_df["scraped_at"], errors="coerce")
        .dt.strftime("%m-%d %H:%M")
        .fillna(table_df["scraped_at"].str[:16])
    )
    # Convert raw ACCEPT/REJECT to compact symbols
    table_df["ai_verdict"] = table_df["ai_verdict"].map(
        {"ACCEPT": "✓", "REJECT": "✗"}
    ).fillna("—")

    st.subheader(f"Entries ({len(table_df)})")
    event = st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "ai_verdict":  st.column_config.TextColumn("Match", width="small"),
            "tier":        st.column_config.TextColumn("Tier", width="small"),
            "title":       st.column_config.TextColumn("Title", width="medium"),
            "company":     st.column_config.TextColumn("Organisation", width="medium"),
            "location":    st.column_config.TextColumn("Region", width="small"),
            "date_posted": st.column_config.TextColumn("Date", width="small"),
            "site":        st.column_config.TextColumn("Origin", width="small"),
            "applied":     st.column_config.CheckboxColumn("Processed", width="small"),
            "scraped_at":  st.column_config.TextColumn("Updated", width="small"),
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
        cur_applied = _is_applied(job.get("applied", "False"))
        new_applied = st.checkbox("✅ Mark as processed", value=cur_applied, key=f"chk_{job['job_url']}")
        if new_applied != cur_applied:
            update_applied(job["job_url"], new_applied)
            st.rerun()

        st.write("")

        url = job.get("job_url", "")
        if url:
            st.link_button("🔗 Open", url)

        cv_p = str(job.get("cv_path", ""))
        if cv_p and Path(cv_p).exists():
            with open(cv_p, "rb") as f:
                st.download_button(
                    "📄 File A",
                    data=f.read(),
                    file_name=f"FileA_{_safe_filename(job['company'])}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        else:
            if not load_settings().get("cv_path"):
                st.caption("Set base file path in Options to enable processing.")
            else:
                st.caption("File A not generated yet.")

        cl_p = str(job.get("cover_letter_path", ""))
        if cl_p and Path(cl_p).exists():
            with open(cl_p, "rb") as f:
                st.download_button(
                    "📝 File B",
                    data=f.read(),
                    file_name=f"FileB_{_safe_filename(job['company'])}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

        # Screening verdict
        ai_verdict = str(job.get("ai_verdict", ""))
        if ai_verdict == "ACCEPT":
            st.success(f"✓ Match  ·  {job.get('ai_confidence', '')} confidence")
        elif ai_verdict == "REJECT":
            st.error(f"✗ No match  ·  {job.get('ai_confidence', '')} confidence")
        ai_reason = str(job.get("ai_reason", "")).strip()
        if ai_reason:
            st.caption(ai_reason)
        ai_flag = str(job.get("ai_flag", "")).strip()
        if ai_flag:
            st.caption(f"⚠ {ai_flag}")

        st.divider()
        tier_label = get_tier(str(job.get("company", "")))
        if tier_label:
            st.caption(tier_label)
        st.caption(f"Origin: {_SITE_DISPLAY.get(job.get('site', ''), job.get('site', '—'))}")
        st.caption(f"Date: {job.get('date_posted', '—')}")
        st.caption(f"Updated: {str(job.get('scraped_at', ''))[:16]}")
        st.caption(f"Ref: {job.get('search_term', '—')}")

        # CV generation diagnostics (only available for jobs processed this session)
        diag = st.session_state.get("cv_diagnostics", {}).get(str(job.get("job_url", "")))
        if diag:
            with st.expander("⚙️ Diagnostics", expanded=False):
                v = diag.get("verification", {})
                status_icon = "✓" if v.get("passed") else "✗"
                st.caption(f"Verification: {status_icon} {'passed' if v.get('passed') else 'FAILED'}")
                st.caption(f"Source: {Path(diag['base_cv_path']).name}  ({diag['file_size_source']} B)")
                st.caption(f"Output: {diag['file_size_output']} B  |  {diag['paragraph_count']} paragraphs")
                st.caption(f"Marker found: {'✓' if diag['marker_found'] else '✗ NOT FOUND'}")
                st.caption(f"Keywords injected: {diag['keywords_count']}")
                st.caption(f"Attempts: {diag['attempts']}")
                if not v.get("passed"):
                    failed = [k for k, val in v.items() if k != "passed" and not val]
                    st.caption(f"Failed checks: {', '.join(failed)}")

    with left:
        cover_text = str(job.get("cover_letter_text", "")).strip()

        if cover_text and not cover_text.startswith("[Error"):
            st.subheader("Note")
            st.markdown(
                f"""<div style="
                    background:#f4f5f7;border-radius:6px;padding:20px 24px;
                    font-family:ui-monospace,monospace;font-size:13px;line-height:1.7;
                    white-space:pre-wrap;border:1px solid #dde1e7;color:#3a3f47;">
{html.escape(cover_text)}
                </div>""",
                unsafe_allow_html=True,
            )
        elif cover_text.startswith("[Error"):
            st.warning(cover_text)
            _regen_button(job, left)
        else:
            st.info("No note generated yet.")
            _regen_button(job, left)

        desc = str(job.get("description", "")).strip()
        if desc and desc != "nan":
            with st.expander("Summary", expanded=False):
                st.text(desc[:3000])


def _regen_button(job, col):
    if st.button("🔄 Generate", key=f"regen_{job['job_url']}"):
        settings = load_settings()
        with st.spinner("Generating…"):
            try:
                text = generate_cover_letter(
                    job["title"], job["company"],
                    job.get("description", ""),
                    job.get("location", "Luxembourg"),
                )
                date_str = str(job.get("date_posted", ""))[:10].replace("-", "")
                uhash = url_hash(str(job.get("job_url", "")))
                folder = job_folder(job["company"], job["title"], date_str, uhash)
                cl_path = str(folder / "cover_letter.docx")
                save_cover_letter_docx(text, cl_path)
                update_files(job["job_url"], cover_letter_text=text, cover_letter_path=cl_path)
                st.rerun()
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
