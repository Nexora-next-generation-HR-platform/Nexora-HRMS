from contextlib import contextmanager
from functools import wraps

from flask import render_template, request, redirect, url_for, session, abort, flash


def register(app, get_db, login_required):

    # ---------- helpers ----------

    @contextmanager
    def db_cursor(commit=False):
        db = get_db()
        try:
            with db.cursor() as cur:
                yield cur
            if commit:
                db.commit()
        finally:
            db.close()

    def hr_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != "HR":
                abort(403)
            return f(*args, **kwargs)
        return wrapper

    def current_employee(cur):
        cur.execute(
            "SELECT employee_id, full_name, department, designation "
            "FROM employees WHERE user_id = %s",
            (session["user_id"],))
        return cur.fetchone()

    def recompute_status(progress_percent):
        """Single place that maps a progress number to the ENUM status,
        so employee-side and HR-side updates can never disagree."""
        if progress_percent >= 100:
            return "Completed"
        if progress_percent > 0:
            return "In Progress"
        return "Assigned"

    # ---------- entry point ----------

    @app.route("/page/training")   # explicit route beats the generic /page/<slug>
    @login_required
    def training_home():
        if session.get("role") == "HR":
            return redirect(url_for("training_hr"))
        return redirect(url_for("training_mine"))

    # ---------- employee side ----------

    @app.route("/training/me")
    @login_required
    def training_mine():
        with db_cursor() as cur:
            emp = current_employee(cur)
            assignments = []
            if emp:
                cur.execute(
                    "SELECT ta.assignment_id, ta.progress_percent, ta.status, "
                    "ta.quiz_score, ta.assigned_at, ta.completed_at, "
                    "t.training_id, t.title, t.description, t.material_url "
                    "FROM training_assignments ta "
                    "JOIN trainings t ON t.training_id = ta.training_id "
                    "WHERE ta.employee_id = %s "
                    "ORDER BY (ta.status = 'Completed'), ta.assigned_at DESC",
                    (emp["employee_id"],))
                assignments = cur.fetchall()

        done = sum(1 for a in assignments if a["status"] == "Completed")
        percent = int(done * 100 / len(assignments)) if assignments else 0
        return render_template("training_mine.html", emp=emp, assignments=assignments,
                               done=done, total=len(assignments), percent=percent)

    @app.route("/training/<int:assignment_id>/start", methods=["POST"])
    @login_required
    def training_start(assignment_id):
        with db_cursor(commit=True) as cur:
            emp = current_employee(cur)
            if not emp:
                abort(403)
            # SECURITY: employee_id comes from the SESSION, never from the form —
            # that's what stops employee A from touching employee B's assignment.
            cur.execute(
                "UPDATE training_assignments "
                "SET status = 'In Progress' "
                "WHERE assignment_id = %s AND employee_id = %s AND status = 'Assigned'",
                (assignment_id, emp["employee_id"]))
            if cur.rowcount == 0:
                flash("Assignment not found or already started", "err")
        return redirect(url_for("training_mine"))

    @app.route("/training/<int:assignment_id>/progress", methods=["POST"])
    @login_required
    def training_progress(assignment_id):
        raw = request.form.get("progress_percent", "").strip()
        try:
            progress = max(0, min(100, int(raw)))
        except ValueError:
            flash("Progress must be a number between 0 and 100", "err")
            return redirect(url_for("training_mine"))

        with db_cursor(commit=True) as cur:
            emp = current_employee(cur)
            if not emp:
                abort(403)
            status = recompute_status(progress)
            completed_at_clause = ", completed_at = NOW()" if status == "Completed" else ""
            cur.execute(
                "UPDATE training_assignments "
                "SET progress_percent = %s, status = %s" + completed_at_clause + " "
                "WHERE assignment_id = %s AND employee_id = %s AND status != 'Completed'",
                (progress, status, assignment_id, emp["employee_id"]))
            if cur.rowcount == 0:
                flash("Assignment not found or already completed", "err")
        return redirect(url_for("training_mine"))

    @app.route("/training/<int:assignment_id>/complete", methods=["POST"])
    @login_required
    def training_complete(assignment_id):
        raw_score = request.form.get("quiz_score", "").strip()
        quiz_score = None
        if raw_score:
            try:
                quiz_score = max(0, min(100, int(raw_score)))
            except ValueError:
                flash("Quiz score must be a number", "err")
                return redirect(url_for("training_mine"))

        with db_cursor(commit=True) as cur:
            emp = current_employee(cur)
            if not emp:
                abort(403)
            cur.execute(
                "UPDATE training_assignments "
                "SET status = 'Completed', progress_percent = 100, "
                "quiz_score = %s, completed_at = NOW() "
                "WHERE assignment_id = %s AND employee_id = %s AND status != 'Completed'",
                (quiz_score, assignment_id, emp["employee_id"]))
            if cur.rowcount == 0:
                flash("Assignment not found or already completed", "err")
            else:
                flash("Training marked complete", "ok")
        return redirect(url_for("training_mine"))

    # ---------- HR side ----------

    @app.route("/training/hr")
    @login_required
    @hr_required
    def training_hr():
        with db_cursor() as cur:
            # per-training completion stats
            cur.execute(
                "SELECT t.training_id, t.title, t.description, t.material_url, "
                "COUNT(ta.assignment_id) AS assigned, "
                "COALESCE(SUM(ta.status = 'Completed'), 0) AS completed "
                "FROM trainings t "
                "LEFT JOIN training_assignments ta ON ta.training_id = t.training_id "
                "GROUP BY t.training_id, t.title, t.description, t.material_url "
                "ORDER BY t.training_id DESC")
            trainings = cur.fetchall()

            cur.execute(
                "SELECT employee_id, full_name, department, designation "
                "FROM employees ORDER BY full_name")
            employees = cur.fetchall()

        for t in trainings:
            t["completed"] = int(t["completed"])
            t["percent"] = int(t["completed"] * 100 / t["assigned"]) if t["assigned"] else 0
        return render_template("training_hr.html", trainings=trainings, employees=employees)

    @app.route("/training/new", methods=["POST"])
    @login_required
    @hr_required
    def training_new():
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        material_url = request.form.get("material_url", "").strip()
        if not title or len(title) > 100:
            flash("Title (max 100 chars) is required", "err")
        else:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "INSERT INTO trainings (title, description, material_url, created_by) "
                    "VALUES (%s, %s, %s, %s)",
                    (title, description or None, material_url or None, session["user_id"]))
            flash("Training created", "ok")
        return redirect(url_for("training_hr"))

    @app.route("/training/<int:training_id>/assign", methods=["POST"])
    @login_required
    @hr_required
    def training_assign(training_id):
        employee_ids = request.form.getlist("employee_ids")
        employee_ids = [e for e in employee_ids if e.isdigit()]
        if not employee_ids:
            flash("Select at least one employee", "err")
            return redirect(url_for("training_hr"))

        with db_cursor(commit=True) as cur:
            cur.execute("SELECT training_id FROM trainings WHERE training_id = %s",
                       (training_id,))
            if not cur.fetchone():
                abort(404)

            # Skip employees already assigned to this training instead of
            # letting the query fail — there's no UNIQUE(training_id, employee_id)
            # in the schema, so this check is what prevents duplicate rows.
            cur.execute(
                "SELECT employee_id FROM training_assignments WHERE training_id = %s",
                (training_id,))
            already = {row["employee_id"] for row in cur.fetchall()}
            to_assign = [int(e) for e in employee_ids if int(e) not in already]

            for emp_id in to_assign:
                cur.execute(
                    "INSERT INTO training_assignments (training_id, employee_id) "
                    "VALUES (%s, %s)", (training_id, emp_id))

        skipped = len(employee_ids) - len(to_assign)
        note = f" ({skipped} already assigned, skipped)" if skipped else ""
        flash(f"Assigned to {len(to_assign)} employee(s){note}", "ok")
        return redirect(url_for("training_hr"))
