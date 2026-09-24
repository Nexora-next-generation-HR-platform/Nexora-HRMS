import re
from pypdf import PdfReader
from docx import Document
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


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


def keyword_match(text, skills):
    """Exact skill-level matching (kept from the original scanner)."""
    t = text.lower()
    matched, missing = [], []
    for s in skills:
        pattern = r"(?<![a-z0-9+#])" + re.escape(s) + r"(?![a-z0-9+#])"
        if re.search(pattern, t):
            matched.append(s)
        else:
            missing.append(s)
    return matched, missing


def semantic_similarity(resume_text, job_description):
    """
    TF-IDF + cosine similarity between resume and job description.
    Catches paraphrased/related content that exact keyword matching misses
    (e.g. "built REST APIs" vs "API development").
    Returns a 0-100 score.
    """
    if not resume_text.strip() or not job_description.strip():
        return 0.0

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform([resume_text, job_description])
    similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
    return round(float(similarity) * 100, 2)


def scan(resume_text, skills, job_description="", keyword_weight=0.6):
    """
    Combined score:
      - keyword_weight (default 0.6) -> exact skill match percentage
      - remainder (0.4)              -> TF-IDF semantic similarity to job description

    If job_description is empty, falls back to pure keyword scoring
    (same behavior as the original scanner).
    """
    matched, missing = keyword_match(resume_text, skills)
    keyword_score = round(float(len(matched)) / len(skills) * 100, 2) if skills else 0.0

    if not job_description:
        return {
            "score": keyword_score,
            "keyword_score": keyword_score,
            "semantic_score": None,
            "matched": matched,
            "missing": missing,
        }

    semantic_score = semantic_similarity(resume_text, job_description)
    final_score = round(
        float(keyword_weight * keyword_score + (1 - keyword_weight) * semantic_score), 2
    )

    return {
        "score": final_score,
        "keyword_score": keyword_score,
        "semantic_score": semantic_score,
        "matched": matched,
        "missing": missing,
    }


def decide(score, threshold=60):
    return "shortlisted" if score >= threshold else "rejected"


if __name__ == "__main__":
    # quick manual test
    resume = "Built REST APIs using Flask and worked with MySQL databases. Familiar with Docker."
    job_desc = "Looking for a backend developer experienced in API development, relational databases, and containerization."
    required_skills = parse_skills("Flask, MySQL, Docker, AWS")

    result = scan(resume, required_skills, job_desc)
    print(result)
    print(decide(result["score"]))
