from datetime import date, datetime
from contextlib import contextmanager
from functools import wraps

from flask import render_template, request, redirect, url_for, session, abort, flash

LEAVE_TYPES = ("Casual", "Sick", "Paid")  # must match the ENUM in schema.sql


def register(app, get_db, login_required):

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
        cur.execute("SELECT employee_id, full_name FROM employees WHERE user_id = %s",
                    (session["user_id"],))
        return cur.fetchone()

    # ---------- entry point ----------

    @app.route("/page/leave")
    @login_required
    def leave_home():
        if session.get("role") == "HR":
            return redirect(url_for("leave_hr"))
        return redirect(url_for("leave_mine"))

    # ---------- employee side ----------

    @app.route("/leave/me")
    @login_required
    def leave_mine():
        with db_cursor() as cur:
            emp = current_employee(cur)
            requests = []
            if emp:
                cur.execute(
                    "SELECT leave_id, leave_type, start_date, end_date, reason, "
                    "status, applied_at "
                    "FROM leave_requests WHERE employee_id = %s "
                    "ORDER BY applied_at DESC",
                    (emp["employee_id"],))
                requests = cur.fetchall()
        return render_template("leave_mine.html", emp=emp, requests=requests,
                               leave_types=LEAVE_TYPES)

    @app.route("/leave/apply", methods=["POST"])
    @login_required
    def leave_apply():
        back = redirect(url_for("leave_mine"))
        leave_type = request.form.get("leave_type", "")
        reason = request.form.get("reason", "").strip()[:255]
        raw_start = request.form.get("start_date", "").strip()
        raw_end = request.form.get("end_date", "").strip()

        if leave_type not in LEAVE_TYPES:
            flash("Please choose a valid leave type", "err")
            return back
        try:
            start_date = date.fromisoformat(raw_start)
            end_date = date.fromisoformat(raw_end)
        except ValueError:
            flash("Please enter valid start and end dates", "err")
            return back
        if end_date < start_date:
            flash("End date cannot be before start date", "err")
            return back

        with db_cursor(commit=True) as cur:
            emp = current_employee(cur)
            if not emp:
                abort(403)
            cur.execute(
                "INSERT INTO leave_requests (employee_id, leave_type, start_date, "
                "end_date, reason, status) VALUES (%s, %s, %s, %s, %s, 'Pending')",
                (emp["employee_id"], leave_type, start_date, end_date, reason or None))

        flash("Leave request submitted.", "ok")
        return back

    # ---------- HR side ----------

    @app.route("/leave/hr")
    @login_required
    @hr_required
    def leave_hr():
        with db_cursor() as cur:
            cur.execute(
                "SELECT l.leave_id, l.leave_type, l.start_date, l.end_date, "
                "l.reason, l.status, l.applied_at, "
                "e.full_name, e.department, e.designation "
                "FROM leave_requests l "
                "JOIN employees e ON e.employee_id = l.employee_id "
                "ORDER BY l.status = 'Pending' DESC, l.applied_at DESC")
            requests = cur.fetchall()
        return render_template("leave_hr.html", requests=requests)

    @app.route("/leave/<int:leave_id>/decide", methods=["POST"])
    @login_required
    @hr_required
    def leave_decide(leave_id):
        action = request.form.get("action")
        new_status = "Approved" if action == "approve" else "Rejected" if action == "reject" else None
        back = redirect(url_for("leave_hr"))
        if not new_status:
            flash("Unknown action", "err")
            return back

        with db_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE leave_requests SET status = %s, reviewed_by = %s "
                "WHERE leave_id = %s AND status = 'Pending'",
                (new_status, session["user_id"], leave_id))
            if cur.rowcount == 0:
                flash("Request not found or already decided", "err")
            else:
                flash(f"Leave request {new_status.lower()}.", "ok")
        return back