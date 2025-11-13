Auth module for Anteater game

Files added:
- `auth.py` - contains `signup`, `login`, `ensure_tables`, and helper functions.
- `schema.sql` - SQL DDL to create `players`, `scores`, and `progress` tables.
- `auth_test_cli.py` - small CLI for creating accounts and logging in locally.
- `requirements.txt` - python deps: bcrypt, mysql-connector-python, python-dotenv

Quick start (PowerShell):
1. Install dependencies into your venv:

```powershell
pip install -r requirements.txt
```

2. Create the database (you can run the `schema.sql` with your MySQL client or use the CLI):

```powershell
# using mysql client
mysql -u root -p < schema.sql

# or using the CLI helper (requires DB config env vars set if not defaults)
python auth_test_cli.py schema
```

3. Create an account and login:

```powershell
python auth_test_cli.py signup alice password123
python auth_test_cli.py login alice password123
```

Security notes:
- Passwords are hashed with bcrypt (automatically salted). Store `password_hash` as VARBINARY.
- Use environment variables to configure DB credentials in production. Avoid committing credentials.
- Consider using TLS/SSL for MySQL connections in production and restrict DB user privileges.

Next steps:
- Integrate login/signup GUI into the Pygame main menu.
- Add session token management if running a server or multi-process architecture.
- Add tests and error handling for DB connectivity.
