import os
from dotenv import load_dotenv
load_dotenv()

import pymysql
from werkzeug.security import generate_password_hash

db = pymysql.connect(host=os.environ.get("DB_HOST", "127.0.0.1"), port=int(os.environ.get("DB_PORT", 3308)), user=os.environ.get("DB_USER", "root"), password=os.environ.get("DB_PASSWORD", ""), database="nexora")
cur = db.cursor()
users = [
    ("hr@nexora.com", "hr123", "HR"),
    ("emp@nexora.com", "emp123", "Employee"),
]
for email, pw, role in users:
    cur.execute(
        "INSERT IGNORE INTO users (email, password_hash, role_id) "
        "VALUES (%s, %s, (SELECT role_id FROM roles WHERE role_name = %s))",
        (email, generate_password_hash(pw), role))
db.commit()
db.close()
print("Test users added")
