import re
import shutil
import hashlib
import tempfile
import time
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# Literal string that must exist in the base CV's placeholder paragraph.
# The code finds this paragraph by content, not by position.
MARKER = "[ATS_KEYWORDS_HERE]"


# ── Naming helpers ────────────────────────────────────────────────────────────

def _safe_name(s: str, max_len: int = 40) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", str(s)).strip("_")[:max_len]


def url_hash(job_url: str) -> str:
    """6-char MD5 prefix of the job URL — makes folder names unique per job."""
    return hashlib.md5(job_url.encode()).hexdigest()[:6]


def job_folder(company: str, title: str, date_str: str, uhash: str = "") -> Path:
    suffix = f"_{uhash}" if uhash else ""
    folder_name = f"{_safe_name(company)}_{_safe_name(title)}_{date_str}{suffix}"
    path = Path.home() / "Desktop" / "job_applications" / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Base CV checks ────────────────────────────────────────────────────────────

def check_base_cv(base_cv_path: str) -> dict:
    """Verify the base CV exists, is readable, and contains the ATS marker."""
    p = Path(base_cv_path)
    result = {
        "exists": p.exists(),
        "file_size": 0,
        "readable": False,
        "has_marker": False,
        "error": None,
    }
    if not result["exists"]:
        return result
    result["file_size"] = p.stat().st_size
    try:
        doc = Document(str(p))
        result["readable"] = True
        result["has_marker"] = any(MARKER in para.text for para in doc.paragraphs)
    except Exception as e:
        result["error"] = str(e)
    return result


def copy_base_cv_to_temp(base_cv_path: str) -> str:
    """Copy base CV to the local temp directory (away from OneDrive).
    Validates the copy is complete. Returns the temp path."""
    src = Path(base_cv_path)
    if not src.exists():
        raise FileNotFoundError(f"Base CV not found: {base_cv_path}")

    tmp_path = Path(tempfile.gettempdir()) / "gongzuo_base_cv.docx"
    shutil.copy2(str(src), str(tmp_path))

    src_size = src.stat().st_size
    tmp_size = tmp_path.stat().st_size

    if tmp_size == 0:
        raise IOError(
            f"Temp copy is 0 bytes (source was {src_size} bytes). "
            "OneDrive may have the file locked — try again in a moment."
        )
    if tmp_size < src_size * 0.9:
        raise IOError(
            f"Temp copy size mismatch: got {tmp_size} bytes, "
            f"source is {src_size} bytes. Possible partial copy."
        )
    return str(tmp_path)


# ── XML helpers ───────────────────────────────────────────────────────────────

def _set_para_white_1pt(para, text: str) -> None:
    """Replace all runs in a paragraph with one white 1pt invisible run."""
    for r in para._element.findall(qn('w:r')):
        para._element.remove(r)

    r_el = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')

    for tag, attrs in [
        ('w:rFonts', {'w:ascii': 'Times New Roman', 'w:eastAsia': 'Times New Roman',
                      'w:hAnsi': 'Times New Roman', 'w:cs': 'Times New Roman'}),
        ('w:color',  {'w:val': 'FFFFFF'}),
        ('w:kern',   {'w:val': '0'}),
        ('w:sz',     {'w:val': '2'}),    # 2 half-points = 1pt
        ('w:szCs',   {'w:val': '2'}),
        ('w:shd',    {'w:val': 'clear', 'w:color': 'auto', 'w:fill': 'FFFFFF'}),
    ]:
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        rPr.append(el)

    r_el.append(rPr)
    t = OxmlElement('w:t')
    t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    r_el.append(t)
    para._element.append(r_el)


# ── Verification ──────────────────────────────────────────────────────────────

def _verify(output_path: str, keywords: list) -> dict:
    """Reopen the saved file from disk and verify the injection is correct."""
    p = Path(output_path)
    v = {
        "file_exists":    p.exists(),
        "file_size":      p.stat().st_size if p.exists() else 0,
        "marker_gone":    False,
        "keywords_found": False,
        "correct_format": False,
        "passed":         False,
    }
    if not v["file_exists"] or v["file_size"] == 0:
        return v

    doc = Document(output_path)
    all_texts = [para.text for para in doc.paragraphs]

    v["marker_gone"] = not any(MARKER in t for t in all_texts)

    non_empty = [t for t in all_texts if t.strip()]
    if keywords and non_empty:
        v["keywords_found"] = keywords[0].lower() in non_empty[-1].lower()
    else:
        v["keywords_found"] = True

    # Check formatting on the last non-empty paragraph via raw XML
    for para in reversed(doc.paragraphs):
        if para.text.strip():
            runs = para._element.findall(qn('w:r'))
            if runs:
                rPr = runs[0].find(qn('w:rPr'))
                if rPr is not None:
                    sz_el    = rPr.find(qn('w:sz'))
                    color_el = rPr.find(qn('w:color'))
                    sz_val    = sz_el.get(qn('w:val'))    if sz_el    is not None else None
                    color_val = color_el.get(qn('w:val')) if color_el is not None else None
                    v["correct_format"] = (sz_val == '2' and color_val == 'FFFFFF')
            break

    v["passed"] = all([
        v["file_exists"],
        v["file_size"] > 0,
        v["marker_gone"],
        v["keywords_found"],
        v["correct_format"],
    ])
    return v


# ── Main injection ────────────────────────────────────────────────────────────

def inject_ats_keywords(base_cv_path: str, keywords: list, output_path: str) -> dict:
    """
    Copy base CV, locate the MARKER paragraph by content (not position),
    replace it with keywords, save, verify. Retries once on failure.

    Returns a diagnostics dict. Raises on unrecoverable failure.
    """
    src = Path(base_cv_path)
    if not src.exists():
        raise FileNotFoundError(f"Base CV not found: {base_cv_path}")

    diag = {
        "base_cv_path":    base_cv_path,
        "output_path":     output_path,
        "file_size_source": src.stat().st_size,
        "file_size_output": 0,
        "paragraph_count":  0,
        "marker_found":     False,
        "keywords_count":   len(keywords),
        "verification":     {},
        "attempts":         0,
        "error":            None,
    }

    keyword_text = ", ".join(keywords)

    for attempt in range(1, 3):
        diag["attempts"] = attempt
        try:
            shutil.copy2(str(src), output_path)
            doc = Document(output_path)

            diag["paragraph_count"] = len(doc.paragraphs)

            marker_para = next(
                (p for p in doc.paragraphs if MARKER in p.text), None
            )
            diag["marker_found"] = marker_para is not None

            if not diag["marker_found"]:
                # Not a transient error — retrying won't help
                raise ValueError(
                    f"Marker '{MARKER}' not found in the base CV. "
                    "Open the base CV in Word, replace the placeholder line "
                    f"text with exactly: {MARKER}"
                )

            _set_para_white_1pt(marker_para, keyword_text)
            doc.save(output_path)

            diag["file_size_output"] = Path(output_path).stat().st_size

            v = _verify(output_path, keywords)
            diag["verification"] = v

            if v["passed"]:
                return diag

            failed = [k for k, val in v.items() if k not in ("passed",) and not val]
            if attempt == 2:
                raise RuntimeError(
                    f"CV verification failed after {attempt} attempts. "
                    f"Failed checks: {failed}"
                )
            # Brief pause before retry
            time.sleep(1)

        except (ValueError, FileNotFoundError):
            raise  # no point retrying these
        except Exception as e:
            if attempt == 2:
                diag["error"] = str(e)
                raise
            time.sleep(1)

    return diag  # unreachable; satisfies linter


# ── Cover letter document ─────────────────────────────────────────────────────

def save_cover_letter_docx(text: str, output_path: str) -> str:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        para = doc.add_paragraph()
        run = para.add_run(block)
        run.font.name = "Calibri"
        run.font.size = Pt(11)
        para.paragraph_format.space_after = Pt(10)

    doc.save(output_path)
    return output_path
