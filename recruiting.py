import os, uuid
from functools import wraps
from flask import (render_template, request, redirect, url_for, session,
                   abort, flash, send_from_directory)
from resume_scanner import extract_text, parse_skills, scan

STAGES = ["Applied", "Shortlisted", "Interview", "Selected", "Hired"]

def register(app, get_db, login_required):
    upload_dir = os.path.join(app.root_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    def hr_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != "HR":
                abort(403)
            return f(*args, **kwargs)
        return wrapper

    @app.route("/page/recruiting")
    @login_required
    @hr_required
    def recruiting_redirect():
        return redirect(url_for("recruiting_home"))

    @app.route("/recruiting")
    @login_required
    @hr_required
    def recruiting_home():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT j.job_id, j.title, j.department, j.status, j.created_at, "
                "COUNT(a.application_id) AS applicants "
                "FROM jobs j LEFT JOIN applications a ON a.job_id = j.job_id "
                "GROUP BY j.job_id, j.title, j.department, j.status, j.created_at "
                "ORDER BY j.created_at DESC")
            jobs = cur.fetchall()
        db.close()
        return render_template("recruiting.html", jobs=jobs)

    @app.route("/recruiting/job/new", methods=["POST"])
    @login_required
    @hr_required
    def job_new():
        title = request.form["title"].strip()
        department = request.form.get("department", "").strip()
        description = request.form.get("description", "").strip()
        skills = ", ".join(parse_skills(request.form.get("required_skills", "")))
        try:
            min_score = max(0, min(100, int(request.form.get("min_score", 60))))
        except ValueError:
            min_score = 60
        if title:
            db = get_db()
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO jobs (title, department, description, required_skills, min_score, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (title, department, description, skills, min_score, session["user_id"]))
            db.commit()
            db.close()
        return redirect(url_for("recruiting_home"))

    @app.route("/recruiting/job/<int:job_id>")
    @login_required
    @hr_required
    def job_detail(job_id):
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
            job = cur.fetchone()
            if not job:
                db.close()
                abort(404)
            cur.execute(
                "SELECT a.application_id, a.status, a.applied_at, a.match_score, "
                "a.matched_skills, a.missing_skills, "
                "c.candidate_id, c.full_name, c.email, c.phone, c.resume_path "
                "FROM applications a JOIN candidates c ON a.candidate_id = c.candidate_id "
                "WHERE a.job_id = %s ORDER BY a.applied_at", (job_id,))
            apps = cur.fetchall()
        db.close()
        for a in apps:
            if a["status"] in STAGES and a["status"] != "Hired":
                a["next"] = STAGES[STAGES.index(a["status"]) + 1]
            else:
                a["next"] = None
        return render_template("job_detail.html", job=job, apps=apps)

    @app.route("/recruiting/job/<int:job_id>/toggle", methods=["POST"])
    @login_required
    @hr_required
    def job_toggle(job_id):
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = IF(status='Open','Closed','Open') "
                "WHERE job_id = %s", (job_id,))
        db.commit()
        db.close()
        return redirect(url_for("job_detail", job_id=job_id))

    @app.route("/recruiting/job/<int:job_id>/candidate", methods=["POST"])
    @login_required
    @hr_required
    def candidate_add(job_id):
        name = request.form["full_name"].strip()
        email = request.form["email"].strip()
        phone = request.form.get("phone", "").strip()
        file = request.files.get("resume")
        back = redirect(url_for("job_detail", job_id=job_id))

        if not name or not email:
            flash("Name and email are required", "err")
            return back
        if not file or not file.filename:
            flash("Please upload a resume (PDF or DOCX)", "err")
            return back
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".pdf", ".docx"):
            flash("Resume must be a PDF or DOCX file", "err")
            return back

        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
            job = cur.fetchone()
            if not job:
                db.close()
                abort(404)

            cur.execute("SELECT candidate_id FROM candidates WHERE email = %s", (email,))
            row = cur.fetchone()
            if row:
                cid = row["candidate_id"]
                cur.execute(
                    "SELECT application_id FROM applications WHERE job_id = %s AND candidate_id = %s",
                    (job_id, cid))
                if cur.fetchone():
                    db.close()
                    flash("This candidate already applied to this job", "err")
                    return back

            fname = uuid.uuid4().hex + ext
            path = os.path.join(upload_dir, fname)
            file.save(path)

            if row:
                cur.execute("UPDATE candidates SET full_name=%s, phone=%s, resume_path=%s "
                            "WHERE candidate_id=%s", (name, phone, fname, cid))
            else:
                cur.execute(
                    "INSERT INTO candidates (full_name, email, phone, resume_path) "
                    "VALUES (%s, %s, %s, %s)", (name, email, phone, fname))
                cid = cur.lastrowid

            skills = parse_skills(job["required_skills"])
            status, score, matched, missing = "Applied", None, None, None
            message = "Candidate added. No required skills set for this job, so review manually."

            if skills:
                try:
                    text = extract_text(path)
                except Exception:
                    text = ""
                if len(text.strip()) < 30:
                    message = "Candidate added, but the resume text could not be read (scanned PDF?). Review manually."
                else:
                    result = scan(text, skills, job.get("description", "") or "")
                    score = result["score"]
                    matched, missing = ", ".join(result["matched"]), ", ".join(result["missing"])
                    if score >= job["min_score"]:
                        status = "Shortlisted"
                        message = f"Resume scanned: {score}% match. Auto-SHORTLISTED."
                    else:
                        status = "Rejected"
                        message = f"Resume scanned: {score}% match (needs {job['min_score']}%). Auto-REJECTED."

            cur.execute(
                "INSERT INTO applications (job_id, candidate_id, status, match_score, matched_skills, missing_skills) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (job_id, cid, status, score, matched, missing))
        db.commit()
        db.close()
        flash(message, "ok" if status != "Rejected" else "err")
        return back

    @app.route("/recruiting/resume/<int:candidate_id>")
    @login_required
    @hr_required
    def resume_view(candidate_id):
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT resume_path FROM candidates WHERE candidate_id = %s", (candidate_id,))
            row = cur.fetchone()
        db.close()
        if not row or not row["resume_path"]:
            abort(404)
        return send_from_directory(upload_dir, row["resume_path"])

    @app.route("/recruiting/application/<int:application_id>/move", methods=["POST"])
    @login_required
    @hr_required
    def application_move(application_id):
        action = request.form.get("action")
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT job_id, status FROM applications WHERE application_id = %s",
                        (application_id,))
            row = cur.fetchone()
            if not row:
                db.close()
                abort(404)
            current = row["status"]
            new_status = None
            if action == "reject" and current not in ("Hired", "Rejected"):
                new_status = "Rejected"
            elif action == "shortlist" and current == "Rejected":
                new_status = "Shortlisted"
            elif action == "next" and current in STAGES and current != "Hired":
                new_status = STAGES[STAGES.index(current) + 1]
            if new_status:
                cur.execute("UPDATE applications SET status = %s WHERE application_id = %s",
                            (new_status, application_id))
        db.commit()
        db.close()
        return redirect(url_for("job_detail", job_id=row["job_id"]))
