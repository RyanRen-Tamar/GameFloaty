import sys
import logging
import urllib.parse
from typing import Dict, Optional

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QRect
from PyQt6.QtGui import QGuiApplication # For screen geometry

# Manager Classes
from .core.config_manager import ConfigManager
from .core.hotkey_manager import HotkeyManager
from .core.tray_manager import TrayManager
from .core.web_engine_manager import WebEngineManager
from .core import window_utils # Module import

# UI Classes
from .ui.main_window import MainWindow
from .ui.search_prompt_dialog import SearchPromptDialog, DialogCode
from .ui.webview_popup import WebViewPopup

# Data Models
from .common.data_models import AppSettings, HotkeyConfig, PopupConfig, GameConfig

logger = logging.getLogger(__name__)

class AppLogic(QObject):
    hotkey_pressed_signal = pyqtSignal()

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app

        # Initialize Managers
        self.config_manager = ConfigManager()
        self.web_engine_manager = WebEngineManager()
        # self.window_utils = window_utils # window_utils contains functions, not a class to instantiate

        # HotkeyManager callback will emit a signal to be handled in the main Qt thread
        self.hotkey_manager = HotkeyManager(on_hotkey_pressed_callback=self._emit_hotkey_signal)

        self.tray_manager = TrayManager(
            on_show_settings_callback=self.show_settings_window,
            on_exit_callback=self.exit_application
        )

        # State Variables
        self.settings: Optional[AppSettings] = None
        self.game_configs: Optional[Dict[str, GameConfig]] = None
        self.main_window: Optional[MainWindow] = None
        self.current_popup: Optional[WebViewPopup] = None
        self.last_search_url_str: Optional[str] = None # Store as string for SearchPromptDialog

        # Connect signals
        self.hotkey_pressed_signal.connect(self._handle_hotkey_press_thread_safe)
        logger.info("AppLogic initialized.")

    def start(self):
        logger.info("Starting AppLogic services...")
        try:
            self.web_engine_manager.initialize_webview_environment(self.app)
            self.settings = self.config_manager.load_settings()
            self.game_configs = self.config_manager.load_game_configs()

            if not self.settings.Hotkey:
                logger.error("Hotkey configuration is missing in settings. Cannot register global hotkey.")
            else:
                self.hotkey_manager.register_global_hotkey(self.settings.Hotkey, self._emit_hotkey_signal)

            self.tray_manager.run()
            logger.info("AppLogic services started successfully.")
        except Exception as e:
            logger.critical(f"Critical error during AppLogic start: {e}", exc_info=True)
            # Depending on the error, might want to exit or show a critical error message
            self.exit_application() # Exit if startup fails catastrophically

    def _emit_hotkey_signal(self):
        # This method is called from pynput's thread.
        # Emit a Qt signal to delegate the actual handling to the main Qt thread.
        self.hotkey_pressed_signal.emit()

    def _handle_hotkey_press_thread_safe(self):
        logger.info("Global hotkey pressed (handled in Qt thread).")

        active_window_title = window_utils.get_active_window_title()
        logger.info(f"Active window: '{active_window_title}'")

        matched_game_cfg: Optional[GameConfig] = None
        matched_game_name: Optional[str] = None

        if not self.game_configs:
            logger.warning("Game configurations not loaded. Cannot match game.")
            self.tray_manager.icon.showMessage("GameWikiOverlay", "Game configurations not loaded.", icon=self.tray_manager.icon.Warning)
            return

        for game_name, game_cfg in self.game_configs.items():
            # Simple title matching for now. Could be more sophisticated (e.g., exe name).
            if game_name.lower() in active_window_title.lower():
                matched_game_cfg = game_cfg
                matched_game_name = game_name
                logger.info(f"Matched game: {game_name}")
                break

        if not matched_game_cfg:
            logger.info("No game configuration matched the active window title.")
            # Assuming TrayManager's icon is pystray.Icon, use notify()
            if self.tray_manager.icon:
                 self.tray_manager.icon.notify(f"No configuration for: {active_window_title}", "GameWikiOverlay")
            return

        # Special handling for CS2/Valorant (show cursor, activate existing popup if any)
        # These games often hide the cursor and run fullscreen.
        # This check should come AFTER we know a game is matched, to use its name.
        if matched_game_name and matched_game_name.lower() in ["counter-strike 2", "valorant"]:
            logger.info(f"Special handling for {matched_game_name}: showing cursor.")
            window_utils.show_cursor_until_visible()
            if self.current_popup and self.current_popup.isVisible():
                # Check if current popup URL is related to this game, otherwise open new
                # For now, just reactivate. A more advanced check might be needed.
                logger.info("Popup already visible, activating it.")
                self.current_popup.activateWindow()
                self.current_popup.raise_()
                return # Don't re-open or re-search

        target_url_str: Optional[str] = None

        if not matched_game_cfg.NeedsSearch:
            target_url_str = self._build_url(matched_game_cfg)
            self.last_search_url_str = target_url_str # Update last search even if not searched
        else:
            # Determine parent for dialog (main window if visible, else None for screen center)
            parent_widget = self.main_window if self.main_window and self.main_window.isVisible() else None

            dialog = SearchPromptDialog(
                last_search_term=self.last_search_url_str if matched_game_cfg.BaseUrl not in (self.last_search_url_str or "") else "",
                placeholder_text=f"Search {matched_game_name} Wiki...",
                parent=parent_widget
            )
            result_code, search_term = dialog.exec_dialog()

            if result_code == DialogCode.ACCEPTED:
                if search_term: # Ensure search term is not empty
                    target_url_str = self._build_url(matched_game_cfg, search_term)
                    self.last_search_url_str = target_url_str
                else:
                    logger.info("Search accepted but term was empty.")
                    # Optionally, open base URL or do nothing
                    target_url_str = self._build_url(matched_game_cfg) # Open base URL
                    self.last_search_url_str = target_url_str
            elif result_code == DialogCode.OPEN_LAST:
                if self.last_search_url_str:
                    target_url_str = self.last_search_url_str
                else: # Fallback if last_search_url_str is somehow empty
                    target_url_str = self._build_url(matched_game_cfg)
                    self.last_search_url_str = target_url_str
            elif result_code == DialogCode.REJECTED:
                logger.info("Search prompt was rejected or closed.")
                return # User cancelled

        if target_url_str:
            logger.info(f"Target URL: {target_url_str}")
            if self.current_popup:
                logger.info("Closing existing popup before opening new one.")
                # Disconnect signal to prevent premature saving of old geometry if close is immediate
                try:
                    self.current_popup.popup_closing.disconnect(self._handle_popup_closing)
                except TypeError: # Signal was not connected or already disconnected
                    pass
                self.current_popup.close() # This should trigger its own cleanup via closeEvent
                self.current_popup = None # Ensure it's cleared before new one

            # Use popup config from settings.
            # If window was moved/resized, settings.Popup should have been updated by _handle_popup_closing
            popup_config_to_use = self.settings.Popup

            try:
                shared_profile = self.web_engine_manager.get_shared_profile()
                self.current_popup = WebViewPopup(
                    initial_url=QUrl(target_url_str),
                    popup_config=popup_config_to_use,
                    shared_profile=shared_profile
                )
                self.current_popup.popup_closing.connect(self._handle_popup_closing)
                self.current_popup.show()
                # Ensure cursor is visible for interacting with the popup
                window_utils.show_cursor_until_visible()
            except Exception as e:
                logger.error(f"Failed to create or show WebViewPopup: {e}", exc_info=True)
                if self.tray_manager.icon:
                    self.tray_manager.icon.notify(f"Error opening wiki: {e}", "GameWikiOverlay Error")

    def _build_url(self, game_cfg: GameConfig, search_term: Optional[str] = None) -> str:
        if search_term:
            # Apply KeywordMap if exists
            if game_cfg.KeywordMap:
                mapped_term = game_cfg.KeywordMap.get(search_term.lower(), search_term)
                logger.debug(f"Search term '{search_term}' mapped to '{mapped_term}' using KeywordMap.")
                search_term = mapped_term

            if game_cfg.SearchTemplate:
                # Ensure search_term is URL-encoded for safety
                encoded_search_term = urllib.parse.quote_plus(search_term)
                return game_cfg.SearchTemplate.replace("{query}", encoded_search_term)
            else: # Fallback to base URL + search term if no template but search term provided
                 # This might not be ideal for all wikis, template is preferred.
                return game_cfg.BaseUrl + urllib.parse.quote_plus(search_term)
        return game_cfg.BaseUrl


    def _handle_popup_closing(self, geometry: QRect):
        logger.info(f"Popup window closed. Final geometry: {geometry}")
        if self.settings: # Ensure settings are loaded
            self.settings.Popup.Left = geometry.x()
            self.settings.Popup.Top = geometry.y()
            self.settings.Popup.Width = geometry.width()
            self.settings.Popup.Height = geometry.height()
            self.config_manager.save_settings(self.settings)
            logger.info("Popup geometry saved to settings.")

        # The popup itself will call deleteLater on its components in its closeEvent.
        # We just need to nullify our reference to it.
        if self.current_popup:
            # self.current_popup.deleteLater() # Already handled by popup's closeEvent
            self.current_popup = None

    def show_settings_window(self):
        logger.debug("Request to show settings window.")
        if self.main_window is None or not self.main_window.isVisible(): # Check if deleted or just hidden
            # Recreate if it was closed and deleted
            self.main_window = MainWindow(
                config_manager=self.config_manager,
                on_save_hotkey_callback=self._handle_save_hotkey,
                on_exit_app_callback=self.exit_application
            )
            # Ensure settings are loaded if main_window is freshly created
            if self.settings:
                 self.main_window.load_settings_to_ui(self.settings)
            else: # Should not happen if start() was successful
                 logger.error("Settings not loaded, cannot populate settings window accurately.")
                 # Load them now as a fallback
                 self.settings = self.config_manager.load_settings()
                 self.main_window.load_settings_to_ui(self.settings)

        self.main_window.show_window() # Custom method to show, raise, activate, and center


    def _handle_save_hotkey(self, new_hotkey_config: HotkeyConfig):
        logger.info(f"Hotkey settings saved via MainWindow. New config: {new_hotkey_config.Key} + {new_hotkey_config.Modifiers}")
        if self.settings:
            self.settings.Hotkey = new_hotkey_config
            # MainWindow already saves settings to disk via ConfigManager.
            # We just need to update AppLogic's copy and re-register.
            if self.hotkey_manager.reregister_hotkeys(new_hotkey_config, self._emit_hotkey_signal):
                if self.tray_manager.icon:
                    self.tray_manager.icon.notify("Hotkey updated successfully.", "GameWikiOverlay")
            else:
                if self.tray_manager.icon:
                    self.tray_manager.icon.notify("Failed to update hotkey.", "GameWikiOverlay Warning")
        else:
            logger.error("Settings not available in AppLogic to update hotkey.")


    def exit_application(self):
        logger.info("Initiating application exit...")

        # Ensure current_popup is closed and its geometry saved if it's open
        if self.current_popup and self.current_popup.isVisible():
            logger.info("Closing active popup before exiting...")
            self.current_popup.close() # This will trigger _handle_popup_closing

        # Stop managers
        self.hotkey_manager.stop_listener_if_running()
        self.tray_manager.stop() # Stops the pystray icon and its thread
        self.web_engine_manager.shutdown() # Cleans up prewarmed view etc.

        # Close main window if it exists
        if self.main_window:
            self.main_window.close() # Allow it to handle its closeEvent

        logger.info("AppLogic cleanup finished. Quitting QApplication.")
        self.app.quit()

if __name__ == '__main__':
    # This is primarily for testing AppLogic structure, not full functionality without mocks.
    # A real run would be initiated by a main.py or run.py script.
    QApplication.setOrganizationName("GameWikiOverlayOrg")
    QApplication.setApplicationName("AppLogicTest")

    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                        format='%(asctime)s - [%(levelname)s] %(name)s (%(threadName)s): %(message)s')

    app = QApplication(sys.argv)

    logger.info("Creating AppLogic for testing...")
    app_logic = AppLogic(app)

    # To test AppLogic.start(), we need default config files to exist or be mocked.
    # For example, data_defaults/settings.json and games.json
    # Let's assume they exist with some basic content for this test.

    # Create dummy settings.json if it doesn't exist for ConfigManager to load
    # (This is a simplified version of what ConfigManager's __main__ does)
    # Ensure imports for os and json if this block is to be robust
    import os
    import json
    from PyQt6.QtCore import QTimer # Ensure QTimer is imported for the __main__ block

    cm_test = ConfigManager()
    if not cm_test.default_settings_path.exists():
        os.makedirs(cm_test.default_settings_path.parent, exist_ok=True)
        default_s = AppSettings(Hotkey=HotkeyConfig(Key="F1", Modifiers=["Ctrl"]), Popup=PopupConfig())
        with open(cm_test.default_settings_path, "w") as f:
            f.write(default_s.model_dump_json(indent=4))
        logger.info(f"Created dummy default settings at {cm_test.default_settings_path}")

    if not cm_test.default_games_config_path.exists():
        os.makedirs(cm_test.default_games_config_path.parent, exist_ok=True)
        default_g = { "Test Game": GameConfig(BaseUrl="https://example.com", NeedsSearch=False) }
        with open(cm_test.default_games_config_path, "w") as f:
            json.dump(default_g, f, indent=4) # Use the json import
        logger.info(f"Created dummy default games config at {cm_test.default_games_config_path}")

    app_logic.start()

    logger.info("AppLogic started. Tray icon should be visible (if supported by OS and pystray).")
    logger.info("Global hotkey (e.g., Ctrl+F1 by default) should be active.")
    logger.info("Test by triggering hotkey, opening settings from tray, etc.")

    # Simulate showing settings window after a delay
    QTimer.singleShot(2000, app_logic.show_settings_window)

    # Run the application event loop
    exit_code = app.exec()
    logger.info(f"Application exited with code {exit_code}.")
    sys.exit(exit_code)
