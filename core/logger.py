from datetime import datetime
from PySide6.QtCore import QObject, Signal


class EventLogger(QObject):
    """Persistent SCADA event log backed by SQLite."""

    event_added = Signal(object)

    def __init__(self, database, parent=None):
        super().__init__(parent)
        self.database = database

    def log(self, category: str, message: str):
        now = datetime.now()

        self.database.execute(
            """
            INSERT INTO events(created_at, category, message)
            VALUES (?, ?, ?)
            """,
            (now.isoformat(timespec="seconds"), category, message),
        )

        event = {
            "time": now,
            "category": category,
            "message": message,
        }
        self.event_added.emit(event)

    def recent(self, count: int = 8):
        rows = self.database.query_all(
            """
            SELECT created_at, category, message
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (count,),
        )

        events = []
        for row in reversed(rows):
            events.append(
                {
                    "time": datetime.fromisoformat(row["created_at"]),
                    "category": row["category"],
                    "message": row["message"],
                }
            )
        return events
