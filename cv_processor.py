import re
import shutil
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _safe_name(s: str, max_len: int = 40) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", str(s)).strip("_")[:max_len]


def job_folder(company: str, title: str, date_str: str) -> Path:
    folder_name = f"{_safe_name(company)}_{_safe_name(title)}_{date_str}"
    path = Path.home() / "Desktop" / "job_applications" / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _set_para_white_1pt(para, text: str) -> None:
    """Replace all runs in para with a single white 1pt invisible run."""
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


def inject_ats_keywords(base_cv_path: str, keywords: list, output_path: str) -> str:
    src = Path(base_cv_path)
    if not src.exists():
        raise FileNotFoundError(f"CV not found: {base_cv_path}")

    shutil.copy2(src, output_path)

    if not keywords:
        return output_path

    doc = Document(output_path)

    # The bottom of the CV has two invisible ATS paragraphs (last two non-empty):
    #   second-to-last: static general skills block  — keep text, fix to 1pt
    #   last:           JD-specific placeholder line — replace text, set to 1pt
    non_empty = [p for p in doc.paragraphs if p.text.strip()]
    if len(non_empty) < 2:
        return output_path

    placeholder  = non_empty[-1]
    skills_block = non_empty[-2]

    skills_text = skills_block.text  # read before modifying

    _set_para_white_1pt(placeholder,  ", ".join(keywords))
    _set_para_white_1pt(skills_block, skills_text)

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
