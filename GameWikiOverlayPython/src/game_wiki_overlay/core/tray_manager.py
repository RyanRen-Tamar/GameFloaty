import logging
import threading
from pathlib import Path

try:
    import pystray
    from PIL import Image
except ImportError as e:
    # This allows the rest of the application to potentially run if pystray is not installed,
    # though tray functionality will be missing. Log the error.
    logging.basicConfig(level=logging.ERROR)
    logging.error(f"Pystray or Pillow import failed: {e}. Tray icon functionality will be disabled.")
    pystray = None
    Image = None

logger = logging.getLogger(__name__)

class TrayManager:
    def __init__(self, on_show_settings_callback=None, on_exit_callback=None):
        if not pystray or not Image:
            logger.error("Pystray or Pillow not available. TrayManager cannot be initialized.")
            self.icon = None
            self.icon_image = None # Store the image to prevent garbage collection
            return

        self.on_show_settings_callback = on_show_settings_callback
        self.on_exit_callback = on_exit_callback

        menu_items = (
            pystray.MenuItem("Settings", self._on_show_settings, default=True), # Make settings default action
            pystray.MenuItem("Exit", self._on_exit)
        )

        # Determine icon path relative to this file's location
        # src/game_wiki_overlay/core/tray_manager.py -> ../../ui/assets/app.png
        try:
            base_path = Path(__file__).resolve().parent.parent # This should be src/game_wiki_overlay
            self.icon_path = base_path / "ui" / "assets" / "app.png"

            if not self.icon_path.exists():
                logger.error(f"Icon file not found at {self.icon_path}. Tray icon may not display correctly.")
                # Fallback: pystray might show a default icon or error
                self.icon_image = None
            else:
                self.icon_image = Image.open(self.icon_path)
        except Exception as e:
            logger.error(f"Failed to load icon image from {self.icon_path}: {e}", exc_info=True)
            self.icon_image = None # Fallback

        try:
            self.icon = pystray.Icon(
                "GameWikiOverlay",
                icon=self.icon_image, # pystray handles None image if loading failed
                title="GameWikiOverlay",
                menu=menu_items
            )
        except Exception as e:
            logger.error(f"Failed to create pystray.Icon: {e}", exc_info=True)
            self.icon = None


    def _on_show_settings(self, icon, item):
        logger.info("Settings menu item clicked.")
        if self.on_show_settings_callback:
            try:
                self.on_show_settings_callback()
            except Exception as e:
                logger.error(f"Error in on_show_settings_callback: {e}", exc_info=True)

    def _on_exit(self, icon, item):
        logger.info("Exit menu item clicked.")
        if self.on_exit_callback:
            try:
                self.on_exit_callback() # Application specific exit logic
            except Exception as e:
                logger.error(f"Error in on_exit_callback: {e}", exc_info=True)
        self.stop() # Stop the tray icon itself

    def run(self):
        if not self.icon:
            logger.error("Tray icon not initialized. Cannot run.")
            return
        logger.info("Starting tray icon...")
        # Run in a separate thread so it doesn't block the main application
        # pystray's run_detached() handles thread creation internally.
        try:
            self.icon.run_detached()
            logger.info("Tray icon started.")
        except Exception as e:
            # This might catch issues if pystray has problems with the environment
            # (e.g., no system tray available, common in some CI environments or minimal Linux setups)
            logger.error(f"Failed to run tray icon: {e}", exc_info=True)


    def stop(self):
        if not self.icon:
            # logger.info("Tray icon not initialized or already stopped.") # Too noisy if called multiple times
            return
        logger.info("Stopping tray icon...")
        try:
            self.icon.stop()
            logger.info("Tray icon stopped.")
        except Exception as e:
            logger.error(f"Error stopping tray icon: {e}", exc_info=True)

    def set_tooltip(self, tooltip: str):
        if not self.icon:
            logger.warning("Tray icon not initialized. Cannot set tooltip.")
            return
        try:
            self.icon.title = tooltip
            logger.debug(f"Tray icon tooltip set to: {tooltip}")
        except Exception as e:
            logger.error(f"Error setting tooltip: {e}", exc_info=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if not pystray or not Image:
        logger.error("Pystray or Pillow not installed. Cannot run TrayManager test.")
    else:
        main_event = threading.Event()

        def dummy_show_settings():
            print("Dummy: Show Settings window requested.")
            # In a real app, this would trigger the settings UI

        def dummy_exit_app():
            print("Dummy: Exit application requested.")
            main_event.set() # Signal the main thread to exit

        print("Initializing TrayManager for testing...")
        tray_manager = TrayManager(
            on_show_settings_callback=dummy_show_settings,
            on_exit_callback=dummy_exit_app
        )

        if tray_manager.icon: # Check if icon was successfully created
            print("Running TrayManager...")
            tray_manager.run()

            print("Tray icon should be visible. Main thread will wait for exit signal.")
            print("Right-click the tray icon and select 'Exit' to close this test.")
            try:
                main_event.wait() # Keep main thread alive until exit is called
            except KeyboardInterrupt:
                print("\nKeyboardInterrupt received. Stopping tray icon.")
            finally:
                tray_manager.stop() # Ensure tray is stopped on exit
                print("TrayManager test finished.")
        else:
            print("TrayManager icon could not be initialized. Test cannot run.")
            print("This might be due to missing icon file, pystray/Pillow issues, or no graphical environment.")

        # Give pystray a moment to clean up if it was running
        if tray_manager.icon and tray_manager.icon.HAS_RUN:
             tray_manager.icon._thread.join(timeout=2) # type: ignore
             if tray_manager.icon._thread.is_alive(): # type: ignore
                  logger.warning("Pystray thread did not terminate cleanly.")
