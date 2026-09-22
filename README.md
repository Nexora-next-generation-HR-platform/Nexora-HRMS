# Nexora - HR Management System

HR system with recruiting (auto resume scanner), onboarding & training, and attendance & leave.
Built with Flask + MySQL 8.0 (run via Docker).

## Setup (Linux/Mac)

1. Start MySQL in Docker:

docker run -d --name nexora-mysql
-e MYSQL_ROOT_PASSWORD=Nexora
-e MYSQL_DATABASE=nexora
-p 3308:3306
mysql:8.0

2. Import the schema:
   `mysql -h 127.0.0.1 -P 3308 -u root -pNexora nexora < database/schema.sql`
3. Copy `.env.example` to `.env` and fill in your DB password (and `DB_PORT=3308`)
4. Install packages: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
5. Add test users: `python seed_users.py`
6. Run: `python app.py` and open http://127.0.0.1:5000

## Setup (Windows)

1. Install [MySQL Community Server](https://dev.mysql.com/downloads/mysql/) (set root password to `Nexora` during setup, keep default port 3306), [MySQL Workbench](https://dev.mysql.com/downloads/workbench/), [Python 3.10+](https://www.python.org/downloads/) (check "Add to PATH"), and [Git](https://git-scm.com/download/win)
2. Clone the repo and `cd` into it
3. Import the schema using MySQL Workbench:
   - Open Workbench, connect to your local server (Host: `127.0.0.1`, Port: `3306`, Username: `root`)
   - **File → Open SQL Script** → select `database/schema.sql`
   - Click the lightning bolt icon (or `Ctrl+Shift+Enter`) to execute
4. Copy `.env.example` to `.env` and fill in your DB password (leave `DB_PORT=3306` or remove that line since it's the default)
5. Install packages:
   1.python -m venv venv
   2.venv\Scripts\activate
   3.pip install -r requirements.txt

6. Add test users: `python seed_users.py`
7. Run: `python app.py` and open http://127.0.0.1:5000
