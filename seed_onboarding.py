import os
from dotenv import load_dotenv
load_dotenv()

import pymysql

TASKS = [
    ("Submit ID proof", "Hand a government-issued ID to HR", "Document"),
    ("Sign employment contract", "Sign and return the contract", "Document"),
    ("Read the Code of Conduct", "Read and acknowledge", "Policy"),
    ("Read the Leave Policy", "Read and acknowledge", "Policy"),
    ("Security awareness training", "Complete the intro security module", "Training"),
]

db = pymysql.connect(host=os.environ.get("DB_HOST", "127.0.0.1"),
                     port=int(os.environ.get("DB_PORT", 3308)),
                     user=os.environ.get("DB_USER", "root"),
                     password=os.environ.get("DB_PASSWORD", ""),
                     database="nexora")
cur = db.cursor()

# onboarding_tasks has no UNIQUE key on title, so re-running would duplicate tasks.
# INSERT ... SELECT ... WHERE NOT EXISTS makes the script safe to run repeatedly.
for title, desc, ttype in TASKS:
    cur.execute(
        "INSERT INTO onboarding_tasks (title, description, task_type) "
        "SELECT %s, %s, %s FROM DUAL "
        "WHERE NOT EXISTS (SELECT 1 FROM onboarding_tasks WHERE title = %s)",
        (title, desc, ttype, title))

# The test Employee login (from seed_users.py) needs an employees row,
# otherwise there is nothing to attach a checklist to.
cur.execute("SELECT user_id FROM users WHERE email = %s", ("emp@nexora.com",))
row = cur.fetchone()
if row:
    cur.execute(
        "INSERT IGNORE INTO employees (user_id, full_name, email, department, designation, join_date) "
        "VALUES (%s, 'Test Employee', 'emp@nexora.com', 'Engineering', 'Developer', CURDATE())",
        (row[0],))
    cur.execute("SELECT employee_id FROM employees WHERE user_id = %s", (row[0],))
    emp_id = cur.fetchone()[0]
    # UNIQUE (employee_id, task_id) + INSERT IGNORE = re-runs never double-assign
    cur.execute(
        "INSERT IGNORE INTO employee_onboarding (employee_id, task_id) "
        "SELECT %s, task_id FROM onboarding_tasks", (emp_id,))
else:
    print("emp@nexora.com not found - run seed_users.py first")

db.commit()
db.close()
print("Onboarding seed done")
