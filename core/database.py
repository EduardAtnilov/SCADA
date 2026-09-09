from pathlib import Path
import sqlite3


class Database:
    """Single SQLite connection for the SCADA application."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            project_root = Path(__file__).resolve().parents[1]
            db_path = project_root / "data" / "scada.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")

        self._create_schema()

    def _create_schema(self):
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash BLOB NOT NULL,
                password_salt BLOB NOT NULL,
                role TEXT NOT NULL
                    CHECK(role IN ('Operator', 'Administrator')),
                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK(is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                category TEXT NOT NULL,
                message TEXT NOT NULL
            );
            """
        )

        # The application design allows exactly one Administrator account.
        # Check old databases before creating the database-level constraint.
        admin_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE role = 'Administrator'
            """
        ).fetchone()[0]

        if admin_count > 1:
            raise RuntimeError(
                "The SCADA database contains more than one Administrator. "
                "Only one Administrator is allowed."
            )

        # SQLite enforces the rule too, so a second Administrator cannot be
        # inserted accidentally from another part of the program.
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_users_single_administrator
            ON users(role)
            WHERE role = 'Administrator'
            """
        )

        self.connection.commit()

    def execute(self, sql: str, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        self.connection.commit()
        return cursor

    def query_one(self, sql: str, parameters=()):
        return self.connection.execute(
            sql,
            parameters,
        ).fetchone()

    def query_all(self, sql: str, parameters=()):
        return self.connection.execute(
            sql,
            parameters,
        ).fetchall()

    def close(self):
        self.connection.close()
