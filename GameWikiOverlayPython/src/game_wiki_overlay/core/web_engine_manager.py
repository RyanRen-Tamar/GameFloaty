import sys
import logging

from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QUrl, QTimer

logger = logging.getLogger(__name__)

class WebEngineManager:
    def __init__(self):
        self.shared_profile: QWebEngineProfile = None
        self.prewarmed_view: QWebEngineView = None

        if not logger.hasHandlers():
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')
        logger.info("WebEngineManager initialized.")

    def initialize_webview_environment(self, app: QApplication = None):
        """
        Initializes the Qt WebEngine environment, sets up a shared profile,
        and optionally pre-warms a QWebEngineView.

        Args:
            app (QApplication, optional): The QApplication instance.
                                          Required by Qt WebEngine. Defaults to None.
        """
        if not QApplication.instance():
            logger.error("QApplication instance not found. Qt WebEngine requires an active QApplication.")
            if app is None: # If app wasn't passed, and none exists, this is a critical failure.
                 raise RuntimeError("QApplication must be initialized before WebEngineManager.")

        logger.info("Initializing Qt WebEngine environment...")

        try:
            # Profile Management
            # QWebEngineProfile.defaultProfile() is often sufficient and creates one if none exists.
            # For more control, one might create a new named profile.
            self.shared_profile = QWebEngineProfile.defaultProfile()
            if not self.shared_profile:
                # This case should be rare as defaultProfile usually creates one.
                logger.warning("QWebEngineProfile.defaultProfile() returned None. Creating a new profile.")
                self.shared_profile = QWebEngineProfile("SharedProfile", None) # None parent for top-level profile

            logger.info(f"Using WebEngineProfile: {self.shared_profile.profileName()}")
            logger.info(f"Cache path: {self.shared_profile.cachePath()}")
            logger.info(f"Persistent storage path: {self.shared_profile.persistentStoragePath()}")

            # Configure profile settings
            self.shared_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskCache)
            self.shared_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            # Example: Set a custom user agent if needed
            # self.shared_profile.setHttpUserAgent("GameWikiOverlay/1.0")
            logger.info("Shared profile configured: DiskCache enabled, PersistentCookies allowed.")

            # Pre-warming (Optional but recommended for performance)
            if self.prewarmed_view is None:
                logger.info("Pre-warming QWebEngineView...")
                self.prewarmed_view = QWebEngineView()
                # Assign a new page with the shared profile to the prewarmed view
                page = QWebEnginePage(self.shared_profile, self.prewarmed_view)
                self.prewarmed_view.setPage(page)

                # Load a blank page to initialize the WebEngine process
                self.prewarmed_view.setUrl(QUrl("about:blank"))

                # The view doesn't need to be shown, but it must be kept alive.
                # It's good practice to hide it explicitly if it were ever part of a layout.
                self.prewarmed_view.hide()
                logger.info("QWebEngineView pre-warmed with about:blank and hidden.")
            else:
                logger.info("QWebEngineView already pre-warmed.")

            logger.info("Qt WebEngine environment initialized successfully.")

        except Exception as e:
            logger.error(f"Error during Qt WebEngine environment initialization: {e}", exc_info=True)
            # Depending on severity, may want to raise or handle gracefully
            self.shared_profile = None # Ensure it's None if init failed
            if self.prewarmed_view:
                self.prewarmed_view.deleteLater()
                self.prewarmed_view = None


    def get_shared_profile(self) -> QWebEngineProfile:
        """
        Returns the shared QWebEngineProfile.

        Raises:
            RuntimeError: If the profile has not been initialized.

        Returns:
            QWebEngineProfile: The shared web engine profile.
        """
        if self.shared_profile is None:
            logger.error("Shared profile accessed before initialization.")
            # Optionally, could try to initialize here if app instance is available
            # For now, strict: must be initialized first.
            raise RuntimeError("WebEngineManager's shared profile is not initialized. Call initialize_webview_environment first.")
        return self.shared_profile

    def create_new_view(self, parent_widget=None) -> QWebEngineView:
        """
        Creates a new QWebEngineView with the shared profile.
        This is a helper if the prewarmed view itself is not to be used directly
        or if multiple views are needed.
        """
        if self.shared_profile is None:
            logger.error("Cannot create new view: shared profile is not initialized.")
            raise RuntimeError("Shared profile is not initialized.")

        view = QWebEngineView(parent_widget)
        page = QWebEnginePage(self.shared_profile, view)
        view.setPage(page)
        logger.info("Created new QWebEngineView with shared profile.")
        return view

    def cleanup_prewarmed_view(self):
        """
        Cleans up the pre-warmed QWebEngineView to release resources.
        Should be called on application exit.
        """
        logger.info("Cleaning up pre-warmed QWebEngineView...")
        if self.prewarmed_view:
            try:
                self.prewarmed_view.stop() # Stop any loading
                # The page is owned by the view if set via setPage,
                # but explicit deletion of page first can be safer for profiles.
                page = self.prewarmed_view.page()
                if page:
                    # Disconnect from profile before deleting? Usually not necessary.
                    page.deleteLater()

                self.prewarmed_view.deleteLater() # Ensure Qt handles deletion
                self.prewarmed_view = None
                logger.info("Pre-warmed QWebEngineView cleaned up successfully.")
            except Exception as e:
                logger.error(f"Error during pre-warmed view cleanup: {e}", exc_info=True)
        else:
            logger.info("No pre-warmed QWebEngineView to clean up.")

    def shutdown(self):
        """
        Perform all necessary cleanup for the WebEngineManager.
        """
        logger.info("WebEngineManager shutting down...")
        self.cleanup_prewarmed_view()
        # Profiles are managed by Qt, but if we created a non-default, uniquely named profile,
        # we might consider removing its persistent data if desired, though not typical for default.
        # For defaultProfile(), no explicit cleanup is usually needed beyond what Qt does.
        logger.info("WebEngineManager shutdown complete.")


if __name__ == '__main__':
    # QApplication is essential for Qt WebEngine
    # It's good practice to set OrgName and AppName for QSettings, which WebEngine might use internally
    QApplication.setOrganizationName("GameWikiOverlayOrg")
    QApplication.setApplicationName("GameWikiOverlayPythonTest")

    app = QApplication(sys.argv)

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')

    print("--- Testing WebEngineManager Initialization ---")
    manager = WebEngineManager()

    try:
        manager.initialize_webview_environment(app)

        if manager.shared_profile:
            print(f"Shared Profile Initialized: {manager.shared_profile.profileName()}")
            print(f"  Cache Type: {manager.shared_profile.httpCacheType()}")
            print(f"  Persistent Cookies: {manager.shared_profile.persistentCookiesPolicy()}")
        else:
            print("Shared Profile FAILED to initialize.")

        if manager.prewarmed_view:
            print(f"Prewarmed View Initialized. URL: {manager.prewarmed_view.url().toString()}")
            assert manager.prewarmed_view.page().profile() == manager.shared_profile
        else:
            print("Prewarmed View FAILED to initialize.")

        print("\n--- Testing creation of a new view using shared profile ---")
        # This view is just for testing, will be cleaned up when app exits or manually
        test_view = None
        if manager.shared_profile:
            try:
                test_view = manager.create_new_view()
                test_view.setWindowTitle("Test WebEngineView")
                test_view.setUrl(QUrl("https://www.qt.io"))
                test_view.resize(800, 600)
                # test_view.show() # Uncomment to visually test
                print("Test view created. Set URL to qt.io.")
                # If not shown, it won't actually load much.
                # For a real test, show it and run app.exec() for a bit.
            except Exception as e:
                print(f"Error creating or showing test_view: {e}")
        else:
            print("Skipping test_view creation as shared profile is not available.")

        # To run the app and see the test_view if shown:
        # print("\nApp will run for 5 seconds if test_view was shown...")
        # if test_view and test_view.isVisible():
        #    QTimer.singleShot(5000, app.quit) # Quit after 5 seconds
        #    app.exec()
        # else: # If test_view is not shown, no need to run app.exec() for long
        #    QTimer.singleShot(100, app.quit) # Process events briefly and quit
        #    app.exec()

        # For a non-GUI test, just process events briefly to allow cleanup signals
        QTimer.singleShot(100, app.quit)
        app.exec()


    except RuntimeError as e:
        print(f"RuntimeError during test: {e}")
    except Exception as e:
        print(f"Unexpected exception during test: {e}")
    finally:
        print("\n--- Cleaning up WebEngineManager ---")
        manager.shutdown() # Calls cleanup_prewarmed_view

    print("\nWebEngineManager test finished.")
    # Note: Qt WebEngine processes might linger for a bit after app exits. This is normal.
    sys.exit(0)
