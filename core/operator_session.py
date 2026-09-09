from PySide6.QtCore import QObject, Signal


class OperatorSession(QObject):
    """
    Current authenticated SCADA operator.

    There is intentionally no logout, no Observer mode and no Lock.
    After login, the current operator remains active until another valid
    user successfully authenticates via Change Operator.
    """

    session_changed = Signal()

    def __init__(
        self,
        user_manager,
        event_logger=None,
        parent=None,
    ):
        super().__init__(parent)
        self.user_manager = user_manager
        self.event_logger = event_logger
        self.current_user = None

    @property
    def is_authenticated(self) -> bool:
        return self.current_user is not None

    @property
    def display_name(self) -> str:
        if self.current_user is None:
            return "AUTH REQUIRED"
        return self.current_user["username"]

    @property
    def role(self) -> str | None:
        if self.current_user is None:
            return None
        return self.current_user["role"]

    @property
    def is_admin(self) -> bool:
        return self.role == "Administrator"

    def login(self, username: str, password: str) -> bool:
        if self.current_user is not None:
            return False

        user = self.user_manager.authenticate(
            username,
            password,
        )

        if user is None:
            return False

        self.current_user = user
        self.session_changed.emit()

        if self.event_logger:
            self.event_logger.log(
                "AUTH",
                f'{user["username"]} logged in',
            )

        return True

    def switch_operator(
        self,
        username: str,
        password: str,
    ) -> bool:
        user = self.user_manager.authenticate(
            username,
            password,
        )

        if user is None:
            return False

        previous = self.display_name
        self.current_user = user
        self.session_changed.emit()

        if self.event_logger:
            self.event_logger.log(
                "AUTH",
                f'Operator changed: {previous} -> {user["username"]}',
            )

        return True
