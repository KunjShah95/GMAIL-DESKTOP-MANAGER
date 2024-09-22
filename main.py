import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QListWidget, QLabel, QLineEdit, QMessageBox, 
                             QListWidgetItem, QSplitter, QFrame, QStackedWidget, QCheckBox,
                             QScrollArea, QSlider, QSpinBox, QComboBox, QColorDialog, QTabWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QPalette, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtChart import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class EmailFetcherThread(QThread):
    email_fetched = pyqtSignal(str, str, str, str, str)

    def __init__(self, account_name, service):
        super().__init__()
        self.account_name = account_name
        self.service = service

    def run(self):
        results = self.service.users().messages().list(userId='me', maxResults=10).execute()
        messages = results.get('messages', [])

        for message in messages:
            msg = self.service.users().messages().get(userId='me', id=message['id']).execute()
            subject = next((h['value'] for h in msg['payload']['headers'] if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in msg['payload']['headers'] if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in msg['payload']['headers'] if h['name'] == 'Date'), '')
            snippet = msg['snippet']
            self.email_fetched.emit(self.account_name, sender, subject, date, snippet)

class CustomListWidgetItem(QListWidgetItem):
    def __init__(self, account, sender, subject, date, snippet):
        super().__init__()
        self.account = account
        self.sender = sender
        self.subject = subject
        self.date = date
        self.snippet = snippet
        self.setText(f"{sender}\n{subject}\n{date}\n{snippet}")
        self.setFont(QFont("Roboto", 10))

class IconWidget(QSvgWidget):
    def __init__(self, icon_path, size=24):
        super().__init__()
        self.load(icon_path)
        self.setFixedSize(QSize(size, size))

class DashboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # Total emails
        self.total_emails_label = QLabel("Total Emails: 0")
        self.layout.addWidget(self.total_emails_label)
        
        # Unread emails per account
        self.unread_emails_layout = QVBoxLayout()
        self.layout.addLayout(self.unread_emails_layout)
        
        # Email activity chart
        self.chart_view = self.create_email_activity_chart()
        self.layout.addWidget(self.chart_view)
        
        # Recent important emails
        self.important_emails_list = QListWidget()
        self.layout.addWidget(QLabel("Recent Important Emails:"))
        self.layout.addWidget(self.important_emails_list)

    def create_email_activity_chart(self):
        series = QLineSeries()
        
        # Sample data (replace with actual data later)
        for i in range(7):
            date = datetime.now() - timedelta(days=i)
            series.append(date.timestamp() * 1000, 10 * i)  # Sample data
        
        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("Email Activity (Last 7 Days)")
        
        axis_x = QDateTimeAxis()
        axis_x.setFormat("MMM dd")
        axis_x.setTitleText("Date")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        
        axis_y = QValueAxis()
        axis_y.setTitleText("Number of Emails")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        return chart_view

    def update_dashboard(self, accounts):
        total_emails = 0
        for account, service in accounts.items():
            # Get total emails
            results = service.users().messages().list(userId='me').execute()
            account_total = results.get('resultSizeEstimate', 0)
            total_emails += account_total
            
            # Get unread emails
            results = service.users().messages().list(userId='me', q='is:unread').execute()
            unread_count = results.get('resultSizeEstimate', 0)
            
            # Update or add unread email count for this account
            account_label = self.findChild(QLabel, f"unread_{account}")
            if account_label:
                account_label.setText(f"{account}: {unread_count} unread")
            else:
                new_label = QLabel(f"{account}: {unread_count} unread")
                new_label.setObjectName(f"unread_{account}")
                self.unread_emails_layout.addWidget(new_label)
        
        self.total_emails_label.setText(f"Total Emails: {total_emails}")
        
        # Update important emails (for simplicity, showing latest 5 emails)
        self.important_emails_list.clear()
        for account, service in accounts.items():
            results = service.users().messages().list(userId='me', maxResults=5).execute()
            messages = results.get('messages', [])
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                subject = next((h['value'] for h in msg['payload']['headers'] if h['name'] == 'Subject'), 'No Subject')
                self.important_emails_list.addItem(f"{account}: {subject}")

        # Update chart (replace with actual data collection)
        # This is a placeholder and should be replaced with actual data collection over time
        series = self.chart_view.chart().series()[0]
        series.clear()
        for i in range(7):
            date = datetime.now() - timedelta(days=i)
            series.append(date.timestamp() * 1000, total_emails / 7 * (7-i))  # Sample data

class GmailMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gmail Monitor")
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowIcon(QIcon('gmail_icon.png'))

        self.accounts = {}
        self.dark_mode = False
        self.font_size = 10
        self.refresh_interval = 5  # minutes
        self.emails_to_display = 10
        self.notifications_enabled = True
        self.theme_color = "#1a73e8"  # Default blue color

        self.init_ui()
        self.apply_styles()

        # Set up refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_emails)
        self.refresh_timer.start(self.refresh_interval * 60 * 1000)  # Convert minutes to milliseconds

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Dashboard tab
        self.dashboard = DashboardWidget()
        self.tab_widget.addTab(self.dashboard, "Dashboard")

        # Emails tab
        emails_widget = QWidget()
        emails_layout = QHBoxLayout(emails_widget)
        self.tab_widget.addTab(emails_widget, "Emails")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        emails_layout.addWidget(splitter)

        # Left panel for account management
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_layout = QVBoxLayout(left_panel)
        
        logo_layout = QHBoxLayout()
        logo_icon = IconWidget("gmail_logo.svg", size=32)
        logo_label = QLabel("Gmail Monitor")
        logo_label.setObjectName("logoLabel")
        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_label)
        left_layout.addLayout(logo_layout)

        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText("Enter account name")
        add_account_btn = QPushButton("Add Account")
        add_account_btn.setObjectName("addAccountBtn")
        add_account_btn.clicked.connect(self.add_account)
        add_account_icon = IconWidget("add_account_icon.svg")
        add_account_btn.setIcon(QIcon(add_account_icon.grab()))
        
        self.account_list = QListWidget()
        self.account_list.setObjectName("accountList")
        
        left_layout.addWidget(QLabel("Add Gmail Account:"))
        left_layout.addWidget(self.account_input)
        left_layout.addWidget(add_account_btn)
        left_layout.addWidget(QLabel("Accounts:"))
        left_layout.addWidget(self.account_list)

        # Right panel for email display
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search emails")
        search_btn = QPushButton()
        search_btn.setObjectName("searchBtn")
        search_btn.clicked.connect(self.search_emails)
        search_icon = IconWidget("search_icon.svg")
        search_btn.setIcon(QIcon(search_icon.grab()))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        right_layout.addLayout(search_layout)

        self.email_list = QListWidget()
        self.email_list.setObjectName("emailList")
        right_layout.addWidget(QLabel("Recent Emails:"))
        right_layout.addWidget(self.email_list)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 900])

        # Settings tab
        self.settings_panel = QScrollArea()
        self.settings_panel.setWidgetResizable(True)
        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)

        # Dark Mode
        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.stateChanged.connect(self.toggle_dark_mode)
        settings_layout.addWidget(self.dark_mode_checkbox)

        # Font Size
        font_size_layout = QHBoxLayout()
        font_size_layout.addWidget(QLabel("Font Size:"))
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(8, 16)
        self.font_size_slider.setValue(self.font_size)
        self.font_size_slider.valueChanged.connect(self.change_font_size)
        font_size_layout.addWidget(self.font_size_slider)
        settings_layout.addLayout(font_size_layout)

        # Refresh Interval
        refresh_layout = QHBoxLayout()
        refresh_layout.addWidget(QLabel("Refresh Interval (minutes):"))
        self.refresh_spinbox = QSpinBox()
        self.refresh_spinbox.setRange(1, 60)
        self.refresh_spinbox.setValue(self.refresh_interval)
        self.refresh_spinbox.valueChanged.connect(self.change_refresh_interval)
        refresh_layout.addWidget(self.refresh_spinbox)
        settings_layout.addLayout(refresh_layout)

        # Emails to Display
        emails_display_layout = QHBoxLayout()
        emails_display_layout.addWidget(QLabel("Emails to Display:"))
        self.emails_display_spinbox = QSpinBox()
        self.emails_display_spinbox.setRange(5, 50)
        self.emails_display_spinbox.setValue(self.emails_to_display)
        self.emails_display_spinbox.valueChanged.connect(self.change_emails_to_display)
        emails_display_layout.addWidget(self.emails_display_spinbox)
        settings_layout.addLayout(emails_display_layout)

        # Notifications
        self.notifications_checkbox = QCheckBox("Enable Notifications")
        self.notifications_checkbox.setChecked(self.notifications_enabled)
        self.notifications_checkbox.stateChanged.connect(self.toggle_notifications)
        settings_layout.addWidget(self.notifications_checkbox)

        # Theme Color
        theme_color_layout = QHBoxLayout()
        theme_color_layout.addWidget(QLabel("Theme Color:"))
        self.theme_color_btn = QPushButton()
        self.theme_color_btn.setFixedSize(30, 30)
        self.theme_color_btn.setStyleSheet(f"background-color: {self.theme_color};")
        self.theme_color_btn.clicked.connect(self.change_theme_color)
        theme_color_layout.addWidget(self.theme_color_btn)
        settings_layout.addLayout(theme_color_layout)

        self.settings_panel.setWidget(settings_content)
        self.tab_widget.addTab(self.settings_panel, "Settings")

    def apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {'#202124' if self.dark_mode else '#f5f5f5'};
            }}
            QFrame#leftPanel, QFrame#rightPanel {{
                background-color: {'#303134' if self.dark_mode else '#ffffff'};
                border: 1px solid {'#5f6368' if self.dark_mode else '#e0e0e0'};
            }}
            QLabel {{
                color: {'#e8eaed' if self.dark_mode else '#202124'};
                font-size: {self.font_size}px;
            }}
            QLabel#logoLabel {{
                font-size: {self.font_size + 4}px;
                color: {self.theme_color};
            }}
            QLineEdit {{
                background-color: {'#303134' if self.dark_mode else '#ffffff'};
                color: {'#e8eaed' if self.dark_mode else '#202124'};
                border: 1px solid {'#5f6368' if self.dark_mode else '#dadce0'};
                border-radius: 4px;
                padding: 5px;
                font-size: {self.font_size}px;
            }}
            QPushButton#addAccountBtn, QPushButton#settingsBtn {{
                background-color: {self.theme_color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: {self.font_size}px;
                font-weight: bold;
            }}
            QPushButton#addAccountBtn:hover, QPushButton#settingsBtn:hover {{
                background-color: {QColor(self.theme_color).darker(110).name()};
            }}
            QListWidget {{
                background-color: {'#303134' if self.dark_mode else '#ffffff'};
                color: {'#e8eaed' if self.dark_mode else '#202124'};
                border: 1px solid {'#5f6368' if self.dark_mode else '#e0e0e0'};
                border-radius: 4px;
                font-size: {self.font_size}px;
            }}
            QListWidget::item {{
                padding: 5px;
            }}
            QListWidget::item:selected {{
                background-color: {'#3c4043' if self.dark_mode else '#e8f0fe'};
                color: {'#e8eaed' if self.dark_mode else '#202124'};
            }}
            QTabWidget::pane {{
                border: 1px solid {'#5f6368' if self.dark_mode else '#e0e0e0'};
            }}
            QTabBar::tab {{
                background-color: {'#303134' if self.dark_mode else '#f1f3f4'};
                color: {'#e8eaed' if self.dark_mode else '#202124'};
                border: 1px solid {'#5f6368' if self.dark_mode else '#dadce0'};
                border-bottom-color: {'#5f6368' if self.dark_mode else '#e0e0e0'};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px;
                font-size: {self.font_size}px;
            }}
            QTabBar::tab:selected {{
                background-color: {'#202124' if self.dark_mode else '#ffffff'};
                border-bottom-color: {'#202124' if self.dark_mode else '#ffffff'};
            }}
        """)

    def add_account(self):
        account_name = self.account_input.text()
        if account_name and account_name not in self.accounts:
            creds = None
            token_file = f'token_{account_name}.pickle'

            if os.path.exists(token_file):
                with open(token_file, 'rb') as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)

            service = build('gmail', 'v1', credentials=creds)
            
            # Animate the addition of the new account
            new_item = QListWidgetItem(account_name)
            new_item.setSizeHint(QSize(0, 0))
            self.account_list.addItem(new_item)
            
            animation = QPropertyAnimation(new_item, b"sizeHint")
            animation.setDuration(300)
            animation.setStartValue(QSize(0, 0))
            animation.setEndValue(QSize(new_item.sizeHint().width(), 30))
            animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            animation.start()

            self.accounts[account_name] = service
            self.account_input.clear()

            self.fetch_emails(account_name, service)
            self.dashboard.update_dashboard(self.accounts)
        else:
            QMessageBox.warning(self, "Warning", "Account name is empty or already exists.")

    def fetch_emails(self, account_name, service):
        self.thread = EmailFetcherThread(account_name, service)
        self.thread.email_fetched.connect(self.add_email_to_list)
        self.thread.start()

    def add_email_to_list(self, account_name, sender, subject, date, snippet):
        item = CustomListWidgetItem(account_name, sender, subject, date, snippet)
        self.email_list.addItem(item)

    def search_emails(self):
        query = self.search_input.text().lower()
        for i in range(self.email_list.count()):
            item = self.email_list.item(i)
            if query in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def toggle_dark_mode(self, state):
        self.dark_mode = state == Qt.CheckState.Checked.value
        self.apply_styles()

    def change_font_size(self, size):
        self.font_size = size
        self.apply_styles()

    def change_refresh_interval(self, interval):
        self.refresh_interval = interval
        self.refresh_timer.setInterval(interval * 60 * 1000)

    def change_emails_to_display(self, count):
        self.emails_to_display = count
        self.refresh_emails()

    def toggle_notifications(self, state):
        self.notifications_enabled = state == Qt.CheckState.Checked.value

    def change_theme_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.theme_color = color.name()
            self.theme_color_btn.setStyleSheet(f"background-color: {self.theme_color};")
            self.apply_styles()

    def refresh_emails(self):
        self.email_list.clear()
        for account_name, service in self.accounts.items():
            self.fetch_emails(account_name, service)
        self.dashboard.update_dashboard(self.accounts)

def main():
    app = QApplication(sys.argv)
    window = GmailMonitorApp()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
