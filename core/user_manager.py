import hashlib
import hmac
import re
import secrets


class UserManager:
    """
    User storage and authentication service.

    The SCADA has exactly one Administrator:
    - created only during the first application start;
    - cannot be deleted;
    - cannot be converted to another role.

    Every user created later by the Administrator is an Operator.

    Passwords are never stored in plaintext.
    PBKDF2-HMAC-SHA256 + a random per-user salt is used.
    """

    PASSWORD_ITERATIONS = 310_000

    def __init__(self, database, event_logger=None):
        self.database = database
        self.event_logger = event_logger

    # =========================================================
    # Validation / password hashing
    # =========================================================

    @staticmethod
    def _validate_username(username: str):
        username = username.strip()

        if not re.fullmatch(
            r"[A-Za-z0-9._-]{3,32}",
            username,
        ):
            raise ValueError(
                "Username must contain 3-32 characters: "
                "letters, numbers, '.', '_' or '-'."
            )

        return username

    @staticmethod
    def _validate_password(password: str):
        if len(password) < 8:
            raise ValueError(
                "Password must contain at least 8 characters."
            )

    @classmethod
    def _hash_password(
        cls,
        password: str,
        salt: bytes,
    ) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            cls.PASSWORD_ITERATIONS,
        )

    # =========================================================
    # Queries
    # =========================================================

    def has_users(self) -> bool:
        row = self.database.query_one(
            "SELECT COUNT(*) AS count FROM users"
        )
        return row["count"] > 0

    def list_users(self):
        rows = self.database.query_all(
            """
            SELECT id, username, role, is_active, created_at
            FROM users
            ORDER BY
                CASE WHEN role = 'Administrator' THEN 0 ELSE 1 END,
                username COLLATE NOCASE
            """
        )

        return [dict(row) for row in rows]

    def get_user_by_username(self, username: str):
        row = self.database.query_one(
            """
            SELECT id, username, role, is_active, created_at
            FROM users
            WHERE username = ? COLLATE NOCASE
            """,
            (username.strip(),),
        )

        return dict(row) if row else None

    def _get_user_with_password(self, username: str):
        return self.database.query_one(
            """
            SELECT
                id,
                username,
                password_hash,
                password_salt,
                role,
                is_active,
                created_at
            FROM users
            WHERE username = ? COLLATE NOCASE
            """,
            (username.strip(),),
        )

    def _get_user_by_id(self, user_id: int):
        row = self.database.query_one(
            """
            SELECT id, username, role, is_active, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )

        if row is None:
            raise ValueError("User was not found.")

        return dict(row)

    # =========================================================
    # Authentication
    # =========================================================

    def authenticate(self, username: str, password: str):
        row = self._get_user_with_password(username)

        if row is None or not row["is_active"]:
            return None

        calculated_hash = self._hash_password(
            password,
            row["password_salt"],
        )

        if not hmac.compare_digest(
            calculated_hash,
            row["password_hash"],
        ):
            return None

        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
        }

    # =========================================================
    # First and only Administrator
    # =========================================================

    def create_initial_administrator(
        self,
        username: str,
        password: str,
    ):
        if self.has_users():
            raise ValueError(
                "The initial Administrator can only be created "
                "when the user database is empty."
            )

        return self._create_user(
            username=username,
            password=password,
            role="Administrator",
            actor="SYSTEM",
        )

    # =========================================================
    # Operator management
    # =========================================================

    def create_user(
        self,
        username: str,
        password: str,
        actor: str,
    ):
        """
        Create an Operator.

        There is deliberately no role argument here:
        additional Administrators cannot be created.
        """
        return self._create_user(
            username=username,
            password=password,
            role="Operator",
            actor=actor,
        )

    def _create_user(
        self,
        username: str,
        password: str,
        role: str,
        actor: str,
    ):
        username = self._validate_username(username)
        self._validate_password(password)

        if role not in ("Operator", "Administrator"):
            raise ValueError("Invalid user role.")

        if role == "Administrator":
            existing_admin = self.database.query_one(
                """
                SELECT id
                FROM users
                WHERE role = 'Administrator'
                LIMIT 1
                """
            )

            if existing_admin is not None:
                raise ValueError(
                    "Only one Administrator is allowed."
                )

        if self.get_user_by_username(username):
            raise ValueError(
                f'User "{username}" already exists.'
            )

        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(
            password,
            salt,
        )

        cursor = self.database.execute(
            """
            INSERT INTO users(
                username,
                password_hash,
                password_salt,
                role,
                is_active
            )
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                username,
                password_hash,
                salt,
                role,
            ),
        )

        if self.event_logger:
            self.event_logger.log(
                "AUTH",
                f'User "{username}" created as {role} by {actor}',
            )

        return cursor.lastrowid


    def change_administrator_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        actor: str,
    ):
        """
        Change the single Administrator password.

        The current Administrator password must be verified first.
        """
        target = self._get_user_by_id(user_id)

        if target["role"] != "Administrator":
            raise ValueError(
                "Selected user is not the Administrator."
            )

        if target["username"].lower() != actor.lower():
            raise ValueError(
                "Administrator password can only be changed "
                "by the current Administrator."
            )

        authenticated = self.authenticate(
            actor,
            current_password,
        )

        if (
            authenticated is None
            or authenticated["role"] != "Administrator"
        ):
            raise ValueError(
                "Current Administrator password is incorrect."
            )

        self._validate_password(new_password)

        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(
            new_password,
            salt,
        )

        self.database.execute(
            """
            UPDATE users
            SET password_hash = ?, password_salt = ?
            WHERE id = ?
            """,
            (
                password_hash,
                salt,
                user_id,
            ),
        )

        if self.event_logger:
            self.event_logger.log(
                "AUTH",
                f'Administrator "{actor}" changed own password',
            )

    def reset_operator_password(
        self,
        user_id: int,
        new_password: str,
        admin_username: str,
        admin_password: str,
    ):
        """
        Reset an Operator password.

        The Operator's previous password is not required.
        The current Administrator must confirm the action
        by entering the Administrator password again.
        """
        target = self._get_user_by_id(user_id)

        if target["role"] != "Operator":
            raise ValueError(
                "Selected user is not an Operator."
            )

        authenticated = self.authenticate(
            admin_username,
            admin_password,
        )

        if (
            authenticated is None
            or authenticated["role"] != "Administrator"
        ):
            raise ValueError(
                "Administrator password is incorrect."
            )

        self._validate_password(new_password)

        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(
            new_password,
            salt,
        )

        self.database.execute(
            """
            UPDATE users
            SET password_hash = ?, password_salt = ?
            WHERE id = ?
            """,
            (
                password_hash,
                salt,
                user_id,
            ),
        )

        if self.event_logger:
            self.event_logger.log(
                "AUTH",
                (
                    f'Password reset for "{target["username"]}" '
                    f'by {admin_username}'
                ),
            )

    def delete_user(
        self,
        user_id: int,
        actor: str,
    ):
        target = self._get_user_by_id(user_id)

        if target["role"] == "Administrator":
            raise ValueError(
                "The Administrator account cannot be deleted."
            )

        self.database.execute(
            """
            DELETE FROM users
            WHERE id = ?
            """,
            (user_id,),
        )

        if self.event_logger:
            self.event_logger.log(
                "AUTH",
                f'User "{target["username"]}" deleted by {actor}',
            )
