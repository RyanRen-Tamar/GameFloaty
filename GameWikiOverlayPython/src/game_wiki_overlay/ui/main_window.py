import sys
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QCheckBox, QComboBox, QPushButton, QMessageBox, QGridLayout, QLabel
)
from PyQt6.QtGui import QIcon, QCloseEvent, QGuiApplication
from PyQt6.QtCore import Qt

# Assuming data_models and config_manager are in sibling directories or structured for such imports
try:
    from ..common.data_models import AppSettings, HotkeyConfig, PopupConfig # Added PopupConfig for completeness
    from ..config_manager import ConfigManager
except ImportError:
    # Fallback for direct execution if __name__ == '__main__'
    # This is a common pattern but can be tricky. Ensure PYTHONPATH is set correctly for actual runs.
    logging.warning("Could not import from ..common or ..config_manager. Using placeholder imports for direct script run.")
    # Define minimal placeholder classes if needed for the __main__ block to run without full project structure
    class HotkeyConfig:
        def __init__(self, Key="F1", Modifiers=None):
            self.Key = Key
            self.Modifiers = Modifiers if Modifiers is not None else ["Ctrl"]

    class PopupConfig:
         def __init__(self, Width=800, Height=600, Left=100, Top=100):
            self.Width = Width
            self.Height = Height
            self.Left = Left
            self.Top = Top

    class AppSettings:
        def __init__(self, Hotkey=None, Popup=None):
            self.Hotkey = Hotkey if Hotkey is not None else HotkeyConfig()
            self.Popup = Popup if Popup is not None else PopupConfig()

    class ConfigManager:
        def __init__(self):
            self.dummy_settings = AppSettings()
            logging.info("Using dummy ConfigManager.")
        def load_settings(self):
            return self.dummy_settings
        def save_settings(self, settings):
            self.dummy_settings = settings
            logging.info(f"Dummy ConfigManager: Saved settings - Hotkey: {settings.Hotkey.Key} + {settings.Hotkey.Modifiers}")

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager,
                 on_save_hotkey_callback=None,
                 on_exit_app_callback=None):
        super().__init__()
        self.config_manager = config_manager
        self.on_save_hotkey_callback = on_save_hotkey_callback
        self.on_exit_app_callback = on_exit_app_callback

        self.available_keys = [f"F{i}" for i in range(1, 13)] + \
                              [chr(ord('A') + i) for i in range(26)] + \
                              [str(i) for i in range(10)]

        self.init_ui()
        try:
            settings = self.config_manager.load_settings()
            self.load_settings_to_ui(settings)
        except Exception as e:
            logger.error(f"Failed to load initial settings into UI: {e}", exc_info=True)
            # Fallback to default UI state if load fails

    def init_ui(self):
        self.setWindowTitle("GameWikiOverlay Settings")

        # Icon Path: src/game_wiki_overlay/ui/main_window.py -> ../assets/app.png
        icon_path = Path(__file__).resolve().parent / "assets" / "app.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            logger.warning(f"Application icon not found at {icon_path}")

        self.setMinimumSize(400, 250) # Adjusted minimum size for better layout

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # --- Hotkey Configuration Section ---
        hotkey_group_label = QLabel("Global Hotkey Configuration")
        hotkey_group_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        main_layout.addWidget(hotkey_group_label)

        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows) # Ensures responsiveness

        # Hotkey Modifiers
        self.modifier_checkboxes = {
            "Ctrl": QCheckBox("Ctrl"),
            "Shift": QCheckBox("Shift"),
            "Alt": QCheckBox("Alt"), # Standard name for Alt
            "Win": QCheckBox("Win/Super") # Or "Meta" depending on pynput's expectation
        }
        modifier_layout = QHBoxLayout()
        for mod_name, checkbox in self.modifier_checkboxes.items():
            modifier_layout.addWidget(checkbox)
        form_layout.addRow("Modifiers:", modifier_layout)

        # Hotkey Key
        self.hotkey_combo = QComboBox()
        self.hotkey_combo.addItems(self.available_keys)
        form_layout.addRow("Key:", self.hotkey_combo)

        main_layout.addLayout(form_layout)
        main_layout.addStretch(1) # Pushes buttons to the bottom

        # Buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save and Apply Hotkey")
        self.save_button.clicked.connect(self._save_settings_and_apply)

        self.cancel_button = QPushButton("Hide Window") # Changed from "Cancel"
        self.cancel_button.clicked.connect(self.hide) # Simply hide, don't discard changes without save

        button_layout.addStretch(1) # Push buttons to the right
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def _get_key_display_name(self, key_str: str) -> str:
        # For now, assumes key_str is directly usable as display name
        return key_str

    def _get_key_from_display_name(self, display_name: str) -> str:
        # For now, assumes display_name is directly usable as key_str
        return display_name

    def load_settings_to_ui(self, settings: AppSettings):
        logger.info(f"Loading settings to UI: Hotkey {settings.Hotkey.Key} with Modifiers {settings.Hotkey.Modifiers}")
        for mod_name, checkbox in self.modifier_checkboxes.items():
            # Normalize modifier names for comparison if needed (e.g. "control" vs "Ctrl")
            # For pynput, common names are 'ctrl', 'shift', 'alt', 'cmd' (for Win/Super on macOS) or 'win'
            # We'll assume the strings in HotkeyConfig.Modifiers match checkbox keys for now.
            normalized_mod_in_settings = [m.lower() for m in settings.Hotkey.Modifiers]
            checkbox.setChecked(mod_name.lower() in normalized_mod_in_settings or
                                mod_name in settings.Hotkey.Modifiers)


        key_to_select = self._get_key_display_name(settings.Hotkey.Key)
        if key_to_select in self.available_keys:
            self.hotkey_combo.setCurrentText(key_to_select)
        else:
            logger.warning(f"Hotkey key '{settings.Hotkey.Key}' not found in available keys. UI will show default.")
            # Optionally add it or select a default
            # self.hotkey_combo.addItem(key_to_select) # If you want to add it dynamically
            # self.hotkey_combo.setCurrentText(key_to_select)


    def _save_settings_and_apply(self):
        selected_modifiers = [name for name, checkbox in self.modifier_checkboxes.items() if checkbox.isChecked()]
        # It's important that these names match what pynput expects if these are directly used.
        # E.g., pynput might expect 'ctrl_l' or 'ctrl_r', or just 'ctrl'.
        # For simplicity, we use "Ctrl", "Shift", "Alt", "Win". These might need mapping for pynput.
        # For now, we store them as is.

        selected_key = self._get_key_from_display_name(self.hotkey_combo.currentText())

        new_hotkey_config = HotkeyConfig(Key=selected_key, Modifiers=selected_modifiers)

        try:
            current_settings = self.config_manager.load_settings()
            current_settings.Hotkey = new_hotkey_config
            self.config_manager.save_settings(current_settings)

            if self.on_save_hotkey_callback:
                self.on_save_hotkey_callback(new_hotkey_config)

            QMessageBox.information(self, "Settings Saved", "Hotkey settings have been saved and applied.")
            self.hide()
        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not save settings: {e}")


    def closeEvent(self, event: QCloseEvent):
        # Center the message box on the main window if possible
        # This requires passing `self` as parent to QMessageBox
        reply = QMessageBox(self)
        reply.setWindowTitle("Confirm Action")
        reply.setText("Do you want to exit the application or minimize it to the system tray?")
        reply.setIcon(QMessageBox.Icon.Question)

        exit_button = reply.addButton("Exit Application", QMessageBox.ButtonRole.DestructiveRole)
        minimize_button = reply.addButton("Minimize to Tray", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = reply.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        reply.setDefaultButton(minimize_button) # Default action

        reply.exec()

        if reply.clickedButton() == exit_button:
            logger.info("User chose to exit application from MainWindow.")
            if self.on_exit_app_callback:
                try:
                    self.on_exit_app_callback()
                except Exception as e:
                    logger.error(f"Error in on_exit_app_callback: {e}", exc_info=True)
            event.accept() # Close the window and allow application to exit if this is the last window
        elif reply.clickedButton() == minimize_button:
            logger.info("User chose to minimize to tray from MainWindow.")
            self.hide()
            event.ignore() # Prevent the window from closing
        else: # Cancel or closed dialog
            logger.info("User cancelled action in MainWindow closeEvent.")
            event.ignore()


    def show_window(self):
        self.show()
        # Attempt to bring window to front, platform behavior can vary
        self.raise_()
        self.activateWindow()
        # Center window on current screen
        try:
            screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen_geometry.center() - self.rect().center())
        except Exception as e:
            logger.warning(f"Could not center window: {e}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')
    app = QApplication(sys.argv)

    # Optional QSS Stylesheet for a more modern look
    qss_style = """
    QMainWindow {
        background-color: #f0f0f0; /* Light grey background */
    }
    QLabel {
        font-size: 10pt;
    }
    QCheckBox {
        spacing: 5px; /* Space between checkbox and text */
    }
    QComboBox {
        padding: 5px;
        border: 1px solid #ccc;
        border-radius: 3px;
        min-height: 20px; /* Ensure consistent height */
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 15px;
        border-left-width: 1px;
        border-left-color: darkgray;
        border-left-style: solid;
        border-top-right-radius: 3px;
        border-bottom-right-radius: 3px;
    }
    QPushButton {
        background-color: #007bff; /* Blue */
        color: white;
        font-weight: bold;
        padding: 8px 15px;
        border-radius: 4px;
        border: none; /* No border for a flatter look */
    }
    QPushButton:hover {
        background-color: #0056b3; /* Darker blue */
    }
    QPushButton:pressed {
        background-color: #004085; /* Even darker blue */
    }
    QFormLayout {
        spacing: 10px; /* Spacing between rows */
    }
    """
    app.setStyleSheet(qss_style)

    # Dummy components for testing
    dummy_config_manager = ConfigManager() # Uses the placeholder if imports failed

    # Pre-populate dummy settings to test loading
    initial_hotkey = HotkeyConfig(Key="F5", Modifiers=["Ctrl", "Shift"])
    dummy_config_manager.dummy_settings = AppSettings(Hotkey=initial_hotkey)

    def test_save_hotkey(hotkey_config: HotkeyConfig):
        print(f"Test Callback: Save Hotkey - Key={hotkey_config.Key}, Modifiers={hotkey_config.Modifiers}")

    def test_exit_app():
        print("Test Callback: Exit Application")
        app.quit() # For testing, actually quit the app

    main_window = MainWindow(
        config_manager=dummy_config_manager,
        on_save_hotkey_callback=test_save_hotkey,
        on_exit_app_callback=test_exit_app
    )

    main_window.show_window()
    sys.exit(app.exec())
