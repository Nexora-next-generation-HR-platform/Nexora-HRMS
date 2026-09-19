import re
from pypdf import PdfReader
from docx import Document

def extract_text(path):
    p = path.lower()
    if p.endswith(".pdf"):
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if p.endswith(".docx"):
        doc = Document(path)
        return "\n".join(par.text for par in doc.paragraphs)
    return ""

def parse_skills(raw):
    skills = []
    for s in re.split(r"[,\n;]", raw or ""):
        s = s.strip().lower()
        if s and s not in skills:
            skills.append(s)
    return skills

def scan(text, skills):
    t = text.lower()
    matched, missing = [], []
    for s in skills:
        pattern = r"(?<![a-z0-9+#])" + re.escape(s) + r"(?![a-z0-9+#])"
        if re.search(pattern, t):
            matched.append(s)
        else:
            missing.append(s)
    score = round(len(matched) / len(skills) * 100) if skills else 0
    return score, matched, missing
