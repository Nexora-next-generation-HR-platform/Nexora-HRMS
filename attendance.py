from contextlib import contextmanager
from datetime import date, datetime

from flask import render_template, session, redirect, url_for, flash


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

    def current_employee(cur):
        cur.execute(
            """
            SELECT employee_id, full_name, department, designation
            FROM employees
            WHERE user_id = %s
            """,
            (session["user_id"],),
        )
        return cur.fetchone()

    # ---------------- Attendance page ----------------
    @app.route("/page/attendance")
    @login_required
    def attendance_home():
        with db_cursor() as cur:
            employee = current_employee(cur)

            if not employee:
                return render_template(
                    "attendance.html",
                    employee=None,
                    today=None,
                    history=[],
                    error="No employee profile is linked to your account.",
                )

            cur.execute(
                """
                SELECT attendance_id, work_date, check_in, check_out, status
                FROM attendance
                WHERE employee_id = %s AND work_date = %s
                """,
                (employee["employee_id"], date.today()),
            )
            today = cur.fetchone()

            cur.execute(
                """
                SELECT work_date, check_in, check_out, status
                FROM attendance
                WHERE employee_id = %s
                ORDER BY work_date DESC
                LIMIT 30
                """,
                (employee["employee_id"],),
            )
            history = cur.fetchall()

        return render_template(
            "attendance.html",
            employee=employee,
            today=today,
            history=history,
            error=None,
        )

    # ---------------- Check In ----------------
    @app.route("/attendance/check-in", methods=["POST"])
    @login_required
    def attendance_check_in():
        with db_cursor(commit=True) as cur:
            employee = current_employee(cur)
            if not employee:
                flash("Employee profile not found.", "err")
                return redirect(url_for("attendance_home"))

            today = date.today()
            cur.execute(
                "SELECT attendance_id, check_in FROM attendance "
                "WHERE employee_id = %s AND work_date = %s",
                (employee["employee_id"], today),
            )
            record = cur.fetchone()

            if record and record["check_in"]:
                flash("You have already checked in today.", "err")
                return redirect(url_for("attendance_home"))

            now = datetime.now().time().replace(microsecond=0)

            if record:
                cur.execute(
                    "UPDATE attendance SET check_in = %s, status = 'Present' "
                    "WHERE attendance_id = %s",
                    (now, record["attendance_id"]),
                )
            else:
                cur.execute(
                    "INSERT INTO attendance (employee_id, work_date, check_in, status) "
                    "VALUES (%s, %s, %s, 'Present')",
                    (employee["employee_id"], today, now),
                )

        flash("Check-in recorded successfully.", "ok")
        return redirect(url_for("attendance_home"))

    # ---------------- Check Out ----------------
    @app.route("/attendance/check-out", methods=["POST"])
    @login_required
    def attendance_check_out():
        with db_cursor(commit=True) as cur:
            employee = current_employee(cur)
            if not employee:
                flash("Employee profile not found.", "err")
                return redirect(url_for("attendance_home"))

            cur.execute(
                "SELECT attendance_id, check_in, check_out FROM attendance "
                "WHERE employee_id = %s AND work_date = %s",
                (employee["employee_id"], date.today()),
            )
            record = cur.fetchone()

            if not record or not record["check_in"]:
                flash("You must check in before checking out.", "err")
                return redirect(url_for("attendance_home"))

            if record["check_out"]:
                flash("You have already checked out today.", "err")
                return redirect(url_for("attendance_home"))

            cur.execute(
                "UPDATE attendance SET check_out = %s WHERE attendance_id = %s",
                (datetime.now().time().replace(microsecond=0), record["attendance_id"]),
            )

        flash("Check-out recorded successfully.", "ok")
        return redirect(url_for("attendance_home"))