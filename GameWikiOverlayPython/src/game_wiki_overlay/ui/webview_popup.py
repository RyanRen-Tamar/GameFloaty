import sys
import logging

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel
)
from PyQt6.QtGui import QResizeEvent, QCloseEvent, QFont, QColor, QPalette
from PyQt6.QtCore import Qt, QUrl, QRect, pyqtSignal, QPoint
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    QWebEngineNavigationRequest # For acceptNavigationRequest
)

try:
    from ..common.data_models import PopupConfig
except ImportError:
    logging.warning("Could not import PopupConfig from ..common.data_models. Using placeholder for direct script run.")
    class PopupConfig:
        def __init__(self, Width=800.0, Height=600.0, Left=100.0, Top=100.0):
            self.Width = int(Width)
            self.Height = int(Height)
            self.Left = int(Left)
            self.Top = int(Top)

logger = logging.getLogger(__name__)

class CustomWebEnginePage(QWebEnginePage):
    """
    Custom QWebEnginePage to handle specific behaviors like new window requests.
    """
    def __init__(self, profile: QWebEngineProfile, parent=None):
        if not isinstance(profile, QWebEngineProfile):
            # Fallback if a QObject (like a QWebEngineView) is passed as profile by mistake
            # This can happen if QWebEnginePage(parent_view) is called instead of QWebEnginePage(profile, parent_view)
            logger.warning(f"CustomWebEnginePage received a parent QObject instead of a QWebEngineProfile. Attempting to use default profile.")
            actual_profile = QWebEngineProfile.defaultProfile()
        else:
            actual_profile = profile
        super().__init__(actual_profile, parent)


    # Handles JavaScript window.open() calls
    def createWindow(self, type_: QWebEnginePage.WebWindowType):
        # type_ can be QWebEnginePage.WebWindowType.WebBrowserWindow,
        # QWebEnginePage.WebWindowType.WebBrowserTab, QWebEnginePage.WebWindowType.WebDialog

        # Option 1: Create a new instance of WebViewPopup (complex, needs careful handling)
        # popup_view = WebViewPopup(None, some_default_config, self.profile()) # Needs URL later
        # return popup_view.web_view.page() # Return the new page

        # Option 2: Load in the current view (simplest, effectively ignores window.open intent)
        # This is often undesirable as it navigates the current page away.
        # A better approach for "load in current view" if forced, is to grab the URL from the request.
        # However, createWindow doesn't directly give the URL.
        # The URL is typically set on the page *after* it's returned from createWindow.

        # Option 3: Block new windows opened by JS (return None)
        # logger.info(f"JavaScript window.open() called (type: {type_}). Blocking popup.")
        # return None

        # Option 4: Return self to reuse the current page/view.
        # This will cause the URL intended for the new window to load in the current view.
        logger.info(f"JavaScript window.open() called (type: {type_}). Reusing current page/view.")
        return self # The new URL will be loaded into this page.

    # Handles how links (<a> tags, etc.) are treated, especially target="_blank"
    def acceptNavigationRequest(self, request: QWebEngineNavigationRequest) -> bool:
        # url: QUrl, type: QWebEnginePage.NavigationType, isMainFrame: bool
        url = request.url()
        nav_type = request.navigationType()
        is_main_frame = request.isMainFrame()

        # Check for clicks on links, especially those that might try to open new windows implicitly
        # (e.g., target="_blank" often defaults to this if not handled by createWindow)
        # QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if not is_main_frame: # Indicates something like an iframe or a new window hint
                logger.info(f"Blocked non-main frame link navigation to: {url.toString()}")
                # Potentially emit a signal to open this URL in a new WebViewPopup if desired
                # self.parent().link_clicked_signal.emit(url) # Assuming parent is WebViewPopup
                return False # Block it for now

            # For target="_blank" links, QtWebEngine's default behavior might be to open
            # in the same view if createWindow doesn't provide a new page.
            # We can explicitly load it in the current view or block.
            # If self.view() is available and we want to force load in current view:
            # logger.info(f"Link clicked: {url.toString()}. Loading in current view.")
            # self.view().load(url)
            # return False # We've handled it.

        return super().acceptNavigationRequest(request)


class WebViewPopup(QWidget):
    popup_closing = pyqtSignal(QRect) # Emits final geometry when closing
    # link_clicked_signal = pyqtSignal(QUrl) # Example if we want AppLogic to handle some links

    def __init__(self, initial_url: QUrl, popup_config: PopupConfig,
                 shared_profile: QWebEngineProfile = None, parent=None):
        super().__init__(parent)
        self.popup_config = popup_config

        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool | # Behaves more like a floating tool window
            Qt.WindowType.FramelessWindowHint # If custom title bar is desired, else remove for standard
        )
        # For FramelessWindowHint, you might need to implement custom move/resize
        # For now, let's use standard frame for easier interaction during development.
        # self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.FramelessWindowHint)


        self.setWindowTitle("GameWikiOverlay Browser")
        self.setGeometry(
            self.popup_config.Left,
            self.popup_config.Top,
            self.popup_config.Width,
            self.popup_config.Height
        )
        self.setMinimumSize(300, 200) # Sensible minimum

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # No margins if frameless or for custom title bar
        self.setLayout(main_layout)

        # Web View
        self.web_view = QWebEngineView()

        if shared_profile:
            logger.info("Using shared profile for WebViewPopup.")
            page = CustomWebEnginePage(shared_profile, self.web_view)
        else:
            logger.warning("No shared profile provided to WebViewPopup. Using default (potentially new/separate).")
            # This will use QWebEngineProfile.defaultProfile() implicitly if profile arg is None for CustomWebEnginePage
            page = CustomWebEnginePage(QWebEngineProfile.defaultProfile(), self.web_view)

        self.web_view.setPage(page)

        # Settings for the web view
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True) # Allow JS to open windows (handled by createWindow)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollbarParametersProxyEnabled, False) # Use Qt scrollbars if preferred, else native
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True) # Allow JS full screen

        # How to handle links that would open new windows (e.g. target="_blank")
        # QWebEngineSettings.NavigateOnNewWindowPolicy.Disabled means newWindowRequested signal is emitted.
        # QWebEngineSettings.NavigateOnNewWindowPolicy.Allow means it might try to use createWindow or open externally.
        # QWebEngineSettings.NavigateOnNewWindowPolicy.Ignore (default) - usually loads in same view for target=_blank.
        # We will rely on CustomWebEnginePage.acceptNavigationRequest for fine-grained control if needed.

        main_layout.addWidget(self.web_view)

        # Loading Overlay
        self.loading_overlay = QLabel("Loading...", self) # Parent is self (WebViewPopup)
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.loading_overlay.font()
        font.setPointSize(16)
        font.setBold(True)
        self.loading_overlay.setFont(font)

        # Style the overlay for visibility
        palette = self.loading_overlay.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 180)) # Semi-transparent black background
        palette.setColor(QPalette.ColorRole.WindowText, QColor(Qt.GlobalColor.white)) # White text
        self.loading_overlay.setAutoFillBackground(True)
        self.loading_overlay.setPalette(palette)
        self.loading_overlay.hide()

        # Connect signals
        self.web_view.loadStarted.connect(self._show_loading_overlay)
        self.web_view.loadFinished.connect(self._hide_loading_overlay)
        self.web_view.urlChanged.connect(self._handle_url_changed)
        self.web_view.renderProcessTerminated.connect(self._handle_render_process_crash)
        # self.web_view.page().linkHovered.connect(self._handle_link_hovered) # Example

        if initial_url and initial_url.isValid():
            logger.info(f"Loading initial URL: {initial_url.toString()}")
            self.web_view.setUrl(initial_url)
        else:
            logger.warning("No valid initial URL provided to WebViewPopup.")
            self.web_view.setUrl(QUrl("about:blank")) # Load a blank page

    def _show_loading_overlay(self):
        logger.debug("Load started, showing loading overlay.")
        self.loading_overlay.setText("Loading...")
        self.loading_overlay.setGeometry(0, 0, self.width(), self.height()) # Ensure it covers the view
        self.loading_overlay.show()
        self.loading_overlay.raise_()

    def _hide_loading_overlay(self, ok: bool):
        logger.debug(f"Load finished. Success: {ok}.")
        if ok:
            self.loading_overlay.hide()
        else:
            # Consider more detailed error from page().loadError() if available
            self.loading_overlay.setText("Failed to load page.")
            self.loading_overlay.show() # Keep it visible with the error
            self.loading_overlay.raise_()


    def _handle_url_changed(self, url: QUrl):
        logger.info(f"WebView URL changed to: {url.toString()}")
        # Could update window title or other UI elements here

    def _handle_render_process_crash(self, processId, status):
        # status is QWebEnginePage.RenderProcessTerminationStatus
        status_map = {
            QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus: "Normal",
            QWebEnginePage.RenderProcessTerminationStatus.AbnormalTerminationStatus: "Abnormal (crash)",
            QWebEnginePage.RenderProcessTerminationStatus.KilledTerminationStatus: "Killed",
            QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus: "Crashed", # Older enum name
        }
        status_str = status_map.get(status, "Unknown")
        logger.error(f"Web render process (ID: {processId}) terminated: {status_str}")
        self.loading_overlay.setText(f"Web process error ({status_str}). Please try reloading or restarting.")
        self.loading_overlay.setGeometry(0, 0, self.width(), self.height())
        self.loading_overlay.show()
        self.loading_overlay.raise_()
        # Optionally, attempt to reload the page or show a button to do so.
        # self.web_view.reload()


    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay') and self.loading_overlay: # Check if init_ui completed
            self.loading_overlay.setGeometry(0, 0, self.width(), self.height())

    def closeEvent(self, event: QCloseEvent):
        logger.info(f"WebViewPopup closing. Emitting geometry: {self.geometry()}")
        self.popup_closing.emit(self.geometry()) # Emit current geometry

        if self.web_view:
            self.web_view.stop()
            page = self.web_view.page()
            if page:
                # Disconnect signals to prevent issues during deletion
                # page.profile().downloadRequested.disconnect() # Example if connected elsewhere
                page.deleteLater()
            self.web_view.deleteLater()
            self.web_view = None # Avoid dangling reference

        super().closeEvent(event)
        logger.debug("WebViewPopup closeEvent completed.")


if __name__ == '__main__':
    # Required for Qt WebEngine
    QApplication.setOrganizationName("GameWikiOverlayOrg")
    QApplication.setApplicationName("WebViewPopupTest")

    app = QApplication(sys.argv)
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')

    # For a full test with a shared profile, WebEngineManager would be needed here.
    # For now, we'll test with the default profile implicitly created by QWebEnginePage.
    # from ..core.web_engine_manager import WebEngineManager # If available
    # web_manager = WebEngineManager()
    # web_manager.initialize_webview_environment(app)
    # shared_profile_instance = web_manager.get_shared_profile()
    shared_profile_instance = QWebEngineProfile.defaultProfile() # Simpler for standalone test

    print("--- Testing WebViewPopup ---")

    initial_config = PopupConfig(Width=1024, Height=768, Left=150, Top=150)
    # test_url = QUrl("https://www.qt.io")
    test_url = QUrl("https://www.google.com") # Google often has complex interactions

    popup = WebViewPopup(
        initial_url=test_url,
        popup_config=initial_config,
        shared_profile=shared_profile_instance
    )

    def handle_popup_closing(geometry: QRect):
        print(f"Test: Popup closing signal received. Geometry: {geometry}")
        # Save this geometry to popup_config for next launch
        initial_config.Left = geometry.x()
        initial_config.Top = geometry.y()
        initial_config.Width = geometry.width()
        initial_config.Height = geometry.height()
        print(f"Updated config: L={initial_config.Left}, T={initial_config.Top}, W={initial_config.Width}, H={initial_config.Height}")

    popup.popup_closing.connect(handle_popup_closing)

    popup.show()
    print(f"WebViewPopup shown with URL: {test_url.toString()}")
    print("Test link clicks, window.open() if any on the page, and general behavior.")
    print("Close the popup window to finish the test.")

    exit_code = app.exec()

    # Cleanup (if web_manager was used)
    # web_manager.shutdown()

    sys.exit(exit_code)
