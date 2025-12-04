"""Simple CLI to test signup/login against the MySQL DB using `auth.py`.

Usage (PowerShell):
    python auth_test_cli.py signup alice password123
    python auth_test_cli.py login alice password123

Make sure DB env vars are set or default DB config matches your local MySQL.
"""
import sys
from auth import ensure_tables, signup, login, get_top_scores, add_score, make_admin


def main():
    if len(sys.argv) < 2:
        print('Usage: auth_test_cli.py <signup|login|schema|topscores|makeadmin> [args]')
        return
    cmd = sys.argv[1]
    if cmd == 'schema':
        ensure_tables()
        print('Ensured tables exist')
    elif cmd == 'signup':
        if len(sys.argv) != 4:
            print('Usage: signup <username> <password>')
            return
        username = sys.argv[2]
        password = sys.argv[3]
        try:
            player_id = signup(username, password)
            print(f'Created player {username} id={player_id}')
        except Exception as e:
            print('Signup failed:', e)
    elif cmd == 'login':
        if len(sys.argv) != 4:
            print('Usage: login <username> <password>')
            return
        username = sys.argv[2]
        password = sys.argv[3]
        try:
            player_id = login(username, password)
            print(f'Login ok: player_id={player_id}')
        except Exception as e:
            print('Login failed:', e)
    elif cmd == 'topscores':
        rows = get_top_scores()
        for r in rows:
            print(r)
    elif cmd == 'addscore':
        if len(sys.argv) != 4:
            print('Usage: addscore <player_id> <score>')
            return
        pid = int(sys.argv[2])
        s = int(sys.argv[3])
        add_score(pid, s)
        print('score added')
    elif cmd == 'makeadmin':
        if len(sys.argv) != 3:
            print('Usage: makeadmin <username>')
            return
        username = sys.argv[2]
        try:
            make_admin(username)
            print(f'Made {username} an admin')
        except Exception as e:
            print('Make admin failed:', e)
    else:
        print('unknown command')


if __name__ == '__main__':
    main()
