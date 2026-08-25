from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
)


class Header(QWidget):

    def __init__(self):
        super().__init__()

        self.setFixedHeight(60)

        self.setStyleSheet("""
            QWidget{
                background:#0c2d73;
            }

            QLabel{
                background:transparent;
                color:white;
            }
        """)

        layout = QHBoxLayout(self)

        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(15)

        logo = QLabel("MILK PLANT")
        logo.setStyleSheet("""
            font-size:20px;
            font-weight:bold;
        """)

        title = QLabel("CURD PRODUCTION SCADA")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size:24px;
            font-weight:bold;
        """)

        datetime = QLabel("24.05.2024   10:25:48")
        datetime.setStyleSheet("""
            font-size:15px;
        """)

        operator = QLabel("Operator")
        operator.setStyleSheet("""
            font-size:15px;
        """)

        layout.addWidget(logo)

        layout.addStretch()

        layout.addWidget(title)

        layout.addStretch()

        layout.addWidget(datetime)
        layout.addSpacing(15)
        layout.addWidget(operator)