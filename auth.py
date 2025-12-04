import os
import bcrypt
import mysql.connector
from mysql.connector import errorcode
from datetime import datetime

# Configuration: should be overridden in production by environment variables
DB_CONFIG = {
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'YourRootPass!'),
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'database': os.getenv('DB_NAME', 'anteater_game'),
    'raise_on_warnings': True,
}


def get_db_connection():
    """Return a new MySQL connection using DB_CONFIG."""
    return mysql.connector.connect(**DB_CONFIG)


def ensure_tables():
    """Create the players, scores, and progress tables if they don't exist."""
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS players (
            player_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            password_hash VARBINARY(128) NOT NULL,
            date_created DATETIME NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS scores (
            score_id INT AUTO_INCREMENT PRIMARY KEY,
            player_id INT NOT NULL,
            score INT NOT NULL,
            date DATETIME NOT NULL,
            level INT NOT NULL DEFAULT 1,
            FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS progress (
            progress_id INT AUTO_INCREMENT PRIMARY KEY,
            player_id INT NOT NULL,
            level INT NOT NULL DEFAULT 1,
            achievements JSON DEFAULT (JSON_ARRAY()),
            FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """,
    ]

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for s in ddl:
            cur.execute(s)
        # migration: ensure 'level' column exists on scores (add if missing)
        try:
            cur.execute("ALTER TABLE scores ADD COLUMN level INT NOT NULL DEFAULT 1")
            conn.commit()
        except Exception:
            # ignore if column exists or any other issue; it's a best-effort migration
            conn.rollback()
        
        # migration: ensure 'is_admin' column exists on players (add if missing)
        try:
            cur.execute("ALTER TABLE players ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
            conn.commit()
        except Exception:
            # ignore if column exists or any other issue; it's a best-effort migration
            conn.rollback()
        conn.commit()
    finally:
        cur.close()
        conn.close()


# ---- Auth functions ----
def hash_password(plain_password: str) -> bytes:
    """Hash a plaintext password with bcrypt (automatically salts).

    Returns the hashed password as bytes suitable for storage in VARBINARY.
    """
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    # bcrypt.gensalt() default cost is reasonable; tune with rounds if needed
    salt = bcrypt.gensalt()
    h = bcrypt.hashpw(plain_password, salt)
    return h


def verify_password(plain_password: str, stored_hash: bytes) -> bool:
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_password, stored_hash)
    except Exception:
        return False


def signup(username: str, password: str) -> int:
    """Create a new user account. Returns new player_id on success.

    Raises ValueError on duplicate username or input problems.
    """
    if not username or not password:
        raise ValueError('username and password required')

    pw_hash = hash_password(password)
    created = datetime.utcnow()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO players (username, password_hash, date_created) VALUES (%s, %s, %s)",
                (username, pw_hash, created),
            )
            conn.commit()
            return cur.lastrowid
        except mysql.connector.IntegrityError as e:
            # duplicate username -> unique constraint violation
            raise ValueError('username already exists') from e
    finally:
        cur.close()
        conn.close()


def login(username: str, password: str) -> int:
    """Verify credentials and return player_id on success. Raise ValueError on failure."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT player_id, password_hash FROM players WHERE username = %s", (username,))
        row = cur.fetchone()
        if not row:
            raise ValueError('invalid-username-or-password')
        player_id, pw_hash = row
        if isinstance(pw_hash, memoryview):
            pw_hash = bytes(pw_hash)
        if verify_password(password, pw_hash):
            return player_id
        raise ValueError('invalid-username-or-password')
    finally:
        cur.close()
        conn.close()


# convenience: add score and progress operations
def add_score(player_id: int, score: int, level: int = 1):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO scores (player_id, score, date, level) VALUES (%s, %s, %s, %s)", (player_id, score, datetime.utcnow(), level))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_top_scores(limit: int = 10):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT p.username, s.score, s.level, s.date FROM scores s JOIN players p ON p.player_id = s.player_id ORDER BY s.score DESC LIMIT %s", (limit,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def update_user_credentials(player_id: int, new_username: str, new_password: str):
    """Update username and password for an existing user.
    
    Raises ValueError on duplicate username or input problems.
    """
    if not new_username or not new_password:
        raise ValueError('username and password required')
    
    pw_hash = hash_password(new_password)
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE players SET username = %s, password_hash = %s WHERE player_id = %s",
                (new_username, pw_hash, player_id)
            )
            if cur.rowcount == 0:
                raise ValueError('player not found')
            conn.commit()
        except mysql.connector.IntegrityError as e:
            # duplicate username -> unique constraint violation
            raise ValueError('username already exists') from e
    finally:
        cur.close()
        conn.close()


def is_admin(player_id: int) -> bool:
    """Check if a player is an admin."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM players WHERE player_id = %s", (player_id,))
        row = cur.fetchone()
        return bool(row and row[0]) if row else False
    finally:
        cur.close()
        conn.close()


def delete_user_scores(admin_id: int, target_username: str):
    """Delete all scores for a user (admin only)."""
    if not is_admin(admin_id):
        raise ValueError('admin access required')
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE s FROM scores s JOIN players p ON s.player_id = p.player_id WHERE p.username = %s", (target_username,))
        deleted_count = cur.rowcount
        conn.commit()
        return deleted_count
    finally:
        cur.close()
        conn.close()


def make_admin(username: str):
    """Promote a user to admin status."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE players SET is_admin = TRUE WHERE username = %s", (username,))
        if cur.rowcount == 0:
            raise ValueError('user not found')
        conn.commit()
    finally:
        cur.close()
        conn.close()