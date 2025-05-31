import sys
import logging

# Configure logging early, especially if other modules log at import time.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] %(name)s (%(threadName)s): %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Ensure logs go to stdout
        # Optional: Add FileHandler here if needed
        # logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6 import QtWebEngineCore # Check for its presence
    from PyQt6 import QtWebEngineWidgets # Check for its presence
except ImportError as e:
    # Log this critical error. If a GUI is desired for this, it's tricky before QApplication.
    # For now, console log is primary.
    logger.critical(f"Failed to import critical PyQt6 components: {e}. This application cannot run.")
    logger.critical("Please ensure PyQt6 and PyQt6-WebEngine are correctly installed.")
    # A simple GUI error message can be attempted with tkinter if available as a fallback
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw() # Hide the main tkinter window
        messagebox.showerror("Critical Error", f"Failed to import PyQt6 components: {e}.\nGameWikiOverlayPython cannot run.\nPlease check your Python environment and ensure PyQt6 and PyQt6-WebEngine are installed.")
        root.destroy()
    except ImportError:
        pass # No tkinter, just rely on console output
    sys.exit(1) # Exit if essential components are missing

# Relative import for AppLogic
# This works when running as a module (e.g., python -m game_wiki_overlay.main)
# or if the src directory is in PYTHONPATH.
try:
    from .app_logic import AppLogic
except ImportError as e:
    logger.error(f"Failed to import AppLogic: {e}. Ensure the program is run as a module or PYTHONPATH is set correctly.")
    # Attempt to adjust path for direct script execution from src/game_wiki_overlay
    # This is for convenience during development.
    if __name__ == '__main__' and __package__ is None:
        import os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        logger.info(f"Adjusted sys.path for direct script execution: {sys.path[0]}")
        try:
            # Need to specify package context for relative import to work after path adjustment
            # This is getting complex. The best is to run as module.
            # For now, let's assume `from game_wiki_overlay.app_logic import AppLogic` if running directly.
            # This depends on where `python src/game_wiki_overlay/main.py` is run from.
            # If run from project root: GameWikiOverlayPython/
            # Then `from src.game_wiki_overlay.app_logic import AppLogic` might be needed.
            # This is why `python -m game_wiki_overlay.main` is preferred.

            # Fallback: if still failing, re-raise or exit.
            # For this exercise, we'll assume the environment is set up for `from .app_logic import AppLogic`
            # or the user runs `python -m ...`
            from .app_logic import AppLogic # Retry after path adjustment (less effective this way)
        except ImportError:
             logger.critical(f"Still failed to import AppLogic after path adjustment attempt: {e}. Please check your execution method and PYTHONPATH.")
             sys.exit(1)


def main():
    """
    Main function to initialize and run the GameWikiOverlayPython application.
    """
    logger.info("Application starting...")

    # QApplication Instance
    # It's good practice to set OrgName and AppName for QSettings, which WebEngine might use
    QApplication.setOrganizationName("GameWikiOverlay") # Or your preferred organization name
    QApplication.setApplicationName("GameWikiOverlayPython")
    QApplication.setApplicationVersion("0.1.0") # Initial version

    app = QApplication(sys.argv)

    # Qt WebEngine components check (early exit if not found)
    # WebEngineManager will also perform checks, but an earlier one here can be clearer.
    # The imports at the top already serve as a basic check.
    # No need for further explicit check here if imports were successful.
    logger.info("Qt WebEngine components seem to be available.")

    # AppLogic Instance and Start
    try:
        app_logic = AppLogic(app)
        app_logic.start() # This initializes WebEngine, loads settings, registers hotkeys etc.
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during AppLogic initialization or start: {e}", exc_info=True)
        # Optionally, show a critical error dialog here if app instance is valid
        # For now, exiting.
        sys.exit(1)

    # Qt Event Loop
    logger.info("Starting Qt event loop...")
    exit_code = app.exec()

    # Cleanup is handled by AppLogic.exit_application, which should be triggered by app.quit()
    # or system signals if connected.
    logger.info(f"Application exited with code {exit_code}.")
    sys.exit(exit_code)

if __name__ == '__main__':
    # This makes the script executable.
    # For package execution, `python -m game_wiki_overlay.main` is preferred.
    main()
