import sys
import enum
import logging

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QSizePolicy
)
from PyQt6.QtGui import QIcon, QCloseEvent, QGuiApplication, QFocusEvent, QPalette, QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

logger = logging.getLogger(__name__)

class DialogCode(enum.Enum):
    ACCEPTED = QDialog.DialogCode.Accepted # Typically 1
    REJECTED = QDialog.DialogCode.Rejected # Typically 0
    OPEN_LAST = 2 # Custom code


class SearchPromptDialog(QDialog):
    def __init__(self, last_search_term: str = "", placeholder_text: str = "Search Wiki...", parent=None):
        super().__init__(parent)
        self.last_search_term = last_search_term
        self._dialog_result_code = DialogCode.REJECTED # Default if closed unexpectedly

        self.init_ui(placeholder_text)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) # Important for cleanup

        # QApplication.instance() might be None if called before QApplication is created
        # It's safer to connect this in a method called after app creation, or ensure app exists.
        # For now, assuming app exists when dialog is instantiated in the main flow.
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.focusWindowChanged.connect(self._handle_focus_change)
        else:
            logger.warning("QApplication instance not found during SearchPromptDialog init. Focus handling might fail.")

        self.setStyleSheet(self._get_default_stylesheet())


    def init_ui(self, placeholder_text: str):
        self.setModal(True) # Make it modal to block other windows until handled

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15) # Add some padding

        # Search Input Area
        search_area_layout = QHBoxLayout()

        search_icon_label = QLabel("🔍") # Unicode magnifying glass
        font = search_icon_label.font()
        font.setPointSize(14) # Make icon a bit larger
        search_icon_label.setFont(font)
        search_icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        search_area_layout.addWidget(search_icon_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder_text)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.accept_input)
        self.search_input.setMinimumHeight(30) # Make input field taller
        search_area_layout.addWidget(self.search_input)

        main_layout.addLayout(search_area_layout)

        # Buttons Area
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1) # Push buttons to the right

        self.open_last_button = QPushButton(f"Open Last: '{self.last_search_term}'" if self.last_search_term else "Open Last")
        self.open_last_button.clicked.connect(self._open_last_search)
        self.open_last_button.setDisabled(not bool(self.last_search_term))
        self.open_last_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        buttons_layout.addWidget(self.open_last_button)

        # Standard "Search" button can be useful for accessibility or if user prefers clicking
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.accept_input)
        self.search_button.setDefault(True) # Makes Enter press trigger this if input doesn't handle it
        self.search_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        buttons_layout.addWidget(self.search_button)

        # A cancel button is good practice for dialogs, even frameless ones (via Esc key)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.custom_reject) # Use custom_reject
        self.cancel_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        buttons_layout.addWidget(self.cancel_button)

        main_layout.addLayout(buttons_layout)
        self.setLayout(main_layout)

    def _get_default_stylesheet(self):
        # Basic QSS for styling. Can be overridden or expanded.
        return """
            SearchPromptDialog {
                background-color: rgba(45, 45, 45, 230); /* Darker, slightly more transparent */
                border: 1px solid rgba(100, 100, 100, 200);
                border-radius: 12px; /* Slightly larger radius */
                color: white;
            }
            QLabel {
                color: white; /* Ensure icon is visible */
                background-color: transparent; /* Prevent overriding dialog background */
            }
            QLineEdit {
                background-color: rgba(30, 30, 30, 220);
                border: 1px solid #555; /* Darker border */
                border-radius: 6px; /* Consistent radius */
                padding: 8px; /* More padding */
                color: white;
                font-size: 11pt; /* Slightly larger font */
            }
            QLineEdit:focus {
                border: 1px solid #0078d7; /* Highlight on focus, similar to Windows style */
            }
            QPushButton {
                background-color: #3a3a3a; /* Darker buttons */
                border: 1px solid #666;
                border-radius: 6px;
                padding: 8px 12px; /* More padding */
                color: white;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #777;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #777;
                border-color: #444;
            }
        """

    def _open_last_search(self):
        logger.debug("Open Last action triggered.")
        self._dialog_result_code = DialogCode.OPEN_LAST
        # QDialog.done() calls accept() or reject() which then close the dialog.
        # We need to use QDialog.done() to ensure the exec() loop finishes with this code.
        super().done(self._dialog_result_code.value)


    def accept_input(self):
        logger.debug(f"Input accepted. Search term: '{self.get_search_term()}'")
        self._dialog_result_code = DialogCode.ACCEPTED
        super().done(self._dialog_result_code.value) # Use QDialog's done() to close with code

    def custom_reject(self): # Renamed from reject to avoid clash if super().reject() is called directly
        logger.debug("Dialog rejected by user action (e.g., Cancel button or Esc).")
        self._dialog_result_code = DialogCode.REJECTED
        super().done(self._dialog_result_code.value)

    # Override QDialog.reject() for Esc key and other system-initiated rejections
    def reject(self):
        # This is called on Esc key press or if system tries to reject the dialog
        logger.debug("Dialog reject() called (e.g. Esc pressed or focus lost without explicit action).")
        self._dialog_result_code = DialogCode.REJECTED
        # Call super().reject() which then calls done(QDialog.DialogCode.Rejected)
        super().reject()


    def get_search_term(self) -> str:
        return self.search_input.text().strip()

    def _handle_focus_change(self, new_focus_window):
        # This logic helps close the dialog if it loses focus, which is common for popup search prompts.
        if self.isVisible():
            # Check if the new focus window is part of this dialog (e.g. the QLineEdit itself)
            is_child = False
            if new_focus_window:
                current_widget = new_focus_window
                while current_widget:
                    if current_widget == self:
                        is_child = True
                        break
                    current_widget = current_widget.parent()

            if not is_child and new_focus_window is not None: # new_focus_window can be None if app loses focus globally
                logger.debug(f"Dialog lost focus to '{new_focus_window}'. Rejecting dialog.")
                self.custom_reject() # Use custom_reject to set specific DialogCode
            elif new_focus_window is None and self.isVisible(): # App lost focus globally
                 logger.debug("Application lost global focus. Rejecting dialog.")
                 self.custom_reject()


    def showEvent(self, event):
        super().showEvent(event)
        # Center on screen
        try:
            screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen_geometry.center() - self.frameGeometry().center())
        except Exception as e:
            logger.warning(f"Could not center SearchPromptDialog: {e}")

        # QTimer is used to set focus *after* the dialog is fully shown and event processing is done
        QTimer.singleShot(0, self.search_input.setFocus)
        QTimer.singleShot(0, self.search_input.selectAll) # Optional: select all text if any
        logger.debug("SearchPromptDialog shown, input focused.")


    def keyPressEvent(self, event: QKeyEvent):
        # Handle Esc key explicitly to ensure our custom_reject is called
        if event.key() == Qt.Key.Key_Escape:
            self.custom_reject()
            return
        super().keyPressEvent(event)


    def exec_dialog(self) -> tuple[DialogCode, str]:
        """
        Executes the dialog and returns the result code and search term.
        """
        # self.exec() is blocking and returns the result code set by done()
        result_code_int = self.exec()

        try:
            # Try to map integer result code back to DialogCode enum member
            # This relies on self._dialog_result_code being set by accept_input, _open_last_search, or custom_reject
            # If dialog was closed by system (e.g. focus loss that calls super().reject()), result_code_int might be QDialog.DialogCode.Rejected (0)
            # and self._dialog_result_code might not match if not routed through our custom handlers.
            # The reject() override should handle this.
            final_result_code = DialogCode(result_code_int)
        except ValueError:
            logger.warning(f"Unknown dialog result code: {result_code_int}. Defaulting to REJECTED.")
            final_result_code = DialogCode.REJECTED

        search_term = ""
        if final_result_code == DialogCode.ACCEPTED:
            search_term = self.get_search_term()
        elif final_result_code == DialogCode.OPEN_LAST:
            search_term = self.last_search_term
            # Ensure this is consistent: OPEN_LAST implies using last_search_term, not current input.

        logger.info(f"Dialog finished. Result: {final_result_code}, Search Term: '{search_term}'")
        return final_result_code, search_term


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')
    app = QApplication(sys.argv)

    print("--- Test 1: Dialog with no last search term ---")
    dialog1 = SearchPromptDialog(placeholder_text="Enter your query here...")
    result_code1, term1 = dialog1.exec_dialog()
    print(f"Result 1: Code={result_code1}, Term='{term1}'")

    print("\n--- Test 2: Dialog with a last search term ---")
    dialog2 = SearchPromptDialog(last_search_term="Default Text", placeholder_text="Search again...")
    result_code2, term2 = dialog2.exec_dialog()
    print(f"Result 2: Code={result_code2}, Term='{term2}'")

    # Test focus loss behavior by creating another window (simplified)
    print("\n--- Test 3: Focus loss (manual test) ---")
    print("Dialog will open. Click outside of it to test focus loss rejection.")
    print("NOTE: This test might be tricky in some window managers or if main console takes focus back too quickly.")

    dialog3 = SearchPromptDialog(last_search_term="Focus Test", placeholder_text="Try to make me lose focus")
    # To make this test more robust, one might need to launch a small, non-modal QWidget before dialog3.exec_dialog()
    # For now, this is a manual test instruction.

    # Example of launching a dummy widget to steal focus (optional, can make test complex)
    # dummy_widget = QWidget()
    # dummy_widget.setWindowTitle("Focus Stealer - Click Me")
    # dummy_widget.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint) # Keep it visible
    # dummy_widget.show()
    # QTimer.singleShot(100, lambda: dummy_widget.activateWindow()) # Try to activate it

    result_code3, term3 = dialog3.exec_dialog()
    print(f"Result 3 (Focus Test): Code={result_code3}, Term='{term3}'")

    # if 'dummy_widget' in locals():
    #     dummy_widget.close()

    sys.exit(0) # Use 0 for clean exit, app.exec() is not run here as dialogs are modal.
