import re
import shutil
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def _safe_name(s: str, max_len: int = 40) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", str(s)).strip("_")[:max_len]


def job_folder(company: str, title: str, date_str: str) -> Path:
    folder_name = f"{_safe_name(company)}_{_safe_name(title)}_{date_str}"
    path = Path.home() / "Desktop" / "job_applications" / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def inject_ats_keywords(base_cv_path: str, keywords: list, output_path: str) -> str:
    src = Path(base_cv_path)
    if not src.exists():
        raise FileNotFoundError(f"CV not found: {base_cv_path}")

    shutil.copy2(src, output_path)

    if keywords:
        doc = Document(output_path)
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        para.paragraph_format.space_before = Pt(0)
        para.paragraph_format.space_after = Pt(0)
        run = para.add_run(" | ".join(keywords))
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(1)
        doc.save(output_path)

    return output_path


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
