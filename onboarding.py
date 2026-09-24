import datetime
from contextlib import contextmanager
from functools import wraps

import pymysql
from flask import (render_template, request, redirect, url_for, session,
                   abort, flash)

TASK_TYPES = ("Document", "Policy", "Training")  # must match the ENUM in schema.sql


def register(app, get_db, login_required):

    # ---------- helpers ----------

    @contextmanager
    def db_cursor(commit=False):
        """Open a connection, hand back a cursor, ALWAYS close the connection.
        recruiting.py calls db.close() by hand, which leaks a connection if a
        query raises in between. try/finally makes that impossible."""
        db = get_db()
        try:
            with db.cursor() as cur:
                yield cur
            if commit:          # only reached if the body raised nothing
                db.commit()
        finally:
            db.close()          # closing without commit = implicit rollback

    def hr_required(f):
        # Copied from recruiting.py: it is defined INSIDE recruiting.register(),
        # so it cannot be imported. Refactor into app.py once both modules are stable.
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != "HR":
                abort(403)
            return f(*args, **kwargs)
        return wrapper

    def current_employee(cur):
        """The logged-in user's employees row, or None.
        Onboarding is keyed by employee_id, but the session only has user_id,
        so every employee-side route must translate one into the other."""
        cur.execute("SELECT employee_id, full_name FROM employees WHERE user_id = %s",
                    (session["user_id"],))
        return cur.fetchone()

    # ---------- entry point ----------

    @app.route("/page/onboarding")   # explicit route beats the generic /page/<slug>
    @login_required
    def onboarding_home():
        if session.get("role") == "HR":
            return redirect(url_for("onboarding_hr"))
        return redirect(url_for("onboarding_mine"))

    # ---------- employee side ----------

    @app.route("/onboarding/me")
    @login_required
    def onboarding_mine():
        with db_cursor() as cur:
            emp = current_employee(cur)
            tasks = []
            if emp:
                cur.execute(
                    "SELECT eo.id, eo.status, eo.completed_at, "
                    "t.title, t.description, t.task_type "
                    "FROM employee_onboarding eo "
                    "JOIN onboarding_tasks t ON t.task_id = eo.task_id "
                    "WHERE eo.employee_id = %s ORDER BY t.task_id",
                    (emp["employee_id"],))
                tasks = cur.fetchall()
        done = sum(1 for t in tasks if t["status"] == "Completed")
        percent = int(done * 100 / len(tasks)) if tasks else 0
        return render_template("onboarding_mine.html", emp=emp, tasks=tasks,
                               done=done, percent=percent)

    @app.route("/onboarding/task/<int:row_id>/complete", methods=["POST"])
    @login_required
    def onboarding_complete(row_id):
        with db_cursor(commit=True) as cur:
            emp = current_employee(cur)
            if not emp:
                abort(403)
            # SECURITY: employee_id comes from the SESSION, never from the form.
            # "AND employee_id = %s" is what stops employee A from completing
            # employee B's task by editing the number in the URL.
            cur.execute(
                "UPDATE employee_onboarding "
                "SET status = 'Completed', completed_at = NOW() "
                "WHERE id = %s AND employee_id = %s AND status = 'Pending'",
                (row_id, emp["employee_id"]))
            if cur.rowcount == 0:
                flash("Task not found or already completed", "err")
        return redirect(url_for("onboarding_mine"))

    # ---------- HR side ----------

    @app.route("/onboarding/hr")
    @login_required
    @hr_required
    def onboarding_hr():
        with db_cursor() as cur:
            # progress per employee: LEFT JOIN so employees with 0 tasks still appear
            cur.execute(
                "SELECT e.employee_id, e.full_name, e.department, e.designation, "
                "e.join_date, COUNT(eo.id) AS total, "
                "COALESCE(SUM(eo.status = 'Completed'), 0) AS done "
                "FROM employees e "
                "LEFT JOIN employee_onboarding eo ON eo.employee_id = e.employee_id "
                "GROUP BY e.employee_id, e.full_name, e.department, e.designation, e.join_date "
                "ORDER BY e.employee_id DESC")
            employees = cur.fetchall()

            # "anti-join": hired applications that have NO matching employees row yet
            cur.execute(
                "SELECT a.application_id, c.full_name, c.email, j.title, j.department "
                "FROM applications a "
                "JOIN candidates c ON c.candidate_id = a.candidate_id "
                "JOIN jobs j ON j.job_id = a.job_id "
                "LEFT JOIN employees e ON e.application_id = a.application_id "
                "WHERE a.status = 'Hired' AND e.employee_id IS NULL "
                "ORDER BY a.application_id")
            hires = cur.fetchall()

            cur.execute("SELECT task_id, title, task_type FROM onboarding_tasks ORDER BY task_id")
            tasks = cur.fetchall()

        for e in employees:
            e["done"] = int(e["done"])   # SUM() returns Decimal; make it a plain int
            e["percent"] = int(e["done"] * 100 / e["total"]) if e["total"] else 0
        return render_template("onboarding_hr.html", employees=employees,
                               hires=hires, tasks=tasks, task_types=TASK_TYPES)

    @app.route("/onboarding/start/<int:application_id>", methods=["POST"])
    @login_required
    @hr_required
    def onboarding_start(application_id):
        back = redirect(url_for("onboarding_hr"))
        designation = request.form.get("designation", "").strip()[:100]

        # Never trust the client, even a date picker: validate on the server.
        raw_date = request.form.get("join_date", "").strip()
        try:
            join_date = datetime.date.fromisoformat(raw_date) if raw_date else None
        except ValueError:
            flash("Invalid join date", "err")
            return back

        with db_cursor(commit=True) as cur:
            cur.execute(
                "SELECT a.status, c.full_name, c.email, c.phone, j.department "
                "FROM applications a "
                "JOIN candidates c ON c.candidate_id = a.candidate_id "
                "JOIN jobs j ON j.job_id = a.job_id "
                "WHERE a.application_id = %s", (application_id,))
            row = cur.fetchone()
            if not row:
                abort(404)
            if row["status"] != "Hired":
                flash("Only candidates with status Hired can be onboarded", "err")
                return back

            # Pre-check gives a friendly message. The UNIQUE key on
            # employees.application_id is what actually guarantees no duplicates.
            cur.execute("SELECT employee_id FROM employees WHERE application_id = %s",
                        (application_id,))
            if cur.fetchone():
                flash("This candidate is already onboarded", "err")
                return back

            # Link to an existing login if one has the same email, else leave NULL.
            # ASSUMPTION: only trusted staff create user accounts (there is no signup page).
            cur.execute("SELECT user_id FROM users WHERE email = %s", (row["email"],))
            u = cur.fetchone()
            user_id = u["user_id"] if u else None

            try:
                cur.execute(
                    "INSERT INTO employees (user_id, application_id, full_name, email, "
                    "phone, department, designation, join_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (user_id, application_id, row["full_name"], row["email"],
                     row["phone"], row["department"], designation or None, join_date))
            except pymysql.err.IntegrityError:
                # e.g. that user_id is already linked to a different employee
                flash("Could not create employee (login already linked?)", "err")
                return back
            emp_id = cur.lastrowid

            # One statement: copy every task template into this employee's checklist.
            cur.execute(
                "INSERT INTO employee_onboarding (employee_id, task_id) "
                "SELECT %s, task_id FROM onboarding_tasks", (emp_id,))
            assigned = cur.rowcount

        note = "" if user_id else " No login is linked yet, so they cannot see their checklist."
        flash(f"Onboarding started: {assigned} tasks assigned.{note}",
              "ok" if user_id else "err")
        return back

    @app.route("/onboarding/task/new", methods=["POST"])
    @login_required
    @hr_required
    def onboarding_task_new():
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        task_type = request.form.get("task_type", "")
        if not title or len(title) > 100 or task_type not in TASK_TYPES:
            flash("Title (max 100 chars) and a valid type are required", "err")
        else:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "INSERT INTO onboarding_tasks (title, description, task_type) "
                    "VALUES (%s, %s, %s)", (title, description or None, task_type))
            flash("Task added. It applies to employees onboarded from now on.", "ok")
        return redirect(url_for("onboarding_hr"))
