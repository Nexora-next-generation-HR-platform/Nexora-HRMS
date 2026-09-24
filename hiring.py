import secrets
from werkzeug.security import generate_password_hash

def create_employee(cur, application_id):
    cur.execute("SELECT employee_id FROM employees WHERE application_id = %s", (application_id,))
    if cur.fetchone():
        return "Employee record already exists for this hire."

    cur.execute(
        "SELECT c.full_name, c.email, c.phone, j.department, j.title "
        "FROM applications a "
        "JOIN candidates c ON a.candidate_id = c.candidate_id "
        "JOIN jobs j ON a.job_id = j.job_id "
        "WHERE a.application_id = %s", (application_id,))
    d = cur.fetchone()

    temp = None
    cur.execute("SELECT user_id FROM users WHERE email = %s", (d["email"],))
    u = cur.fetchone()
    if u:
        user_id = u["user_id"]
        cur.execute("SELECT employee_id FROM employees WHERE user_id = %s", (user_id,))
        if cur.fetchone():
            return "This person is already an employee (same email). No new record created."
    else:
        temp = secrets.token_urlsafe(6)
        cur.execute(
            "INSERT INTO users (email, password_hash, role_id) "
            "VALUES (%s, %s, (SELECT role_id FROM roles WHERE role_name = 'Employee'))",
            (d["email"], generate_password_hash(temp)))
        user_id = cur.lastrowid

    cur.execute(
        "INSERT INTO employees (user_id, application_id, full_name, email, phone, department, designation, join_date) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, CURDATE())",
        (user_id, application_id, d["full_name"], d["email"], d["phone"], d["department"], d["title"]))

    if temp:
        return f"Hired! Employee account created. Login: {d['email']} / temp password: {temp} (note it down, it is shown only once)"
    return "Hired! Employee record created and linked to the existing login."
