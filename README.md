# Nexora - HR Management System

HR system with recruiting (auto resume scanner), onboarding & training, and attendance & leave.
Built with Flask + MySQL/MariaDB.

## Setup
1. Create the database: `mariadb -u root -p < database/schema.sql`
2. Copy `.env.example` to `.env` and fill in your DB password
3. Install packages: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
4. Add test users: `python seed_users.py`
5. Run: `python app.py` and open http://127.0.0.1:5000

## Test logins
- HR: hr@nexora.com / hr123
- Employee: emp@nexora.com / emp123
