import platform
import logging
import time

try:
    import pygetwindow
except ImportError:
    pygetwindow = None
    logging.warning("pygetwindow library not found. get_active_window_title will not work.")

# For Windows-specific cursor functions
if platform.system() == "Windows":
    try:
        import ctypes
    except ImportError:
        ctypes = None
        logging.warning("ctypes library not found. Cursor functions will not work on Windows.")
else:
    ctypes = None # Not needed for non-Windows

logger = logging.getLogger(__name__)

def get_active_window_title() -> str:
    """
    Retrieves the title of the currently active window.

    Returns:
        str: The title of the active window, or an empty string if unable to retrieve it
             or if pygetwindow is not available.
    """
    if not pygetwindow:
        logger.debug("pygetwindow not available, cannot get active window title.")
        return ""
    try:
        active_window = pygetwindow.getActiveWindow()
        if active_window:
            return active_window.title
        else:
            logger.debug("No active window found by pygetwindow.")
            return ""
    except pygetwindow.PyGetWindowException as e: # More specific exception if available
        logger.error(f"Error getting active window title (PyGetWindowException): {e}", exc_info=True)
        return ""
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting active window title: {e}", exc_info=True)
        return ""

def show_cursor_until_visible():
    """
    Shows the mouse cursor until it is definitely visible (display count >= 0).
    This function is Windows-specific due to its use of ctypes and user32.dll.
    """
    if platform.system() == "Windows":
        if not ctypes:
            logger.warning("ctypes is not available on Windows. Cannot show cursor.")
            return
        logger.debug("Attempting to show cursor (Windows)...")
        # The ShowCursor function increments or decrements a display counter.
        # Cursor is displayed if counter >= 0.
        # We want to call ShowCursor(True) until the counter is >= 0.
        # ShowCursor returns the new display counter value.
        try:
            display_count = ctypes.windll.user32.ShowCursor(True)
            while display_count < 0: # Keep showing until counter is non-negative
                display_count = ctypes.windll.user32.ShowCursor(True)
                logger.debug(f"Called ShowCursor(True), new display count: {display_count}")
            logger.info(f"Cursor shown. Final display count: {display_count}")
        except Exception as e:
            logger.error(f"Error calling ShowCursor(True): {e}", exc_info=True)
    else:
        logger.info("show_cursor_until_visible is a Windows-specific function. Doing nothing on other OS.")

def hide_cursor_completely():
    """
    Hides the mouse cursor until it is definitely hidden (display count < 0).
    This function is Windows-specific.
    """
    if platform.system() == "Windows":
        if not ctypes:
            logger.warning("ctypes is not available on Windows. Cannot hide cursor.")
            return
        logger.debug("Attempting to hide cursor (Windows)...")
        # Cursor is hidden if display counter < 0.
        # We want to call ShowCursor(False) until the counter is < 0.
        try:
            display_count = ctypes.windll.user32.ShowCursor(False)
            # Continue calling ShowCursor(False) as long as the counter is 0 or more.
            # The counter should eventually become -1, then -2, etc.
            # We typically want it to be at least -1 for it to be considered hidden.
            while display_count >= -1: # Loop until it's truly hidden (e.g., -2 or less, or just < 0)
                                     # Original C# code hides until < 0.
                                     # A single call might make it -1 if it was 0.
                                     # Multiple calls ensure it goes further negative if something else shows it.
                                     # For robustness, let's ensure it's at least -1.
                                     # If it's already < -1, this loop won't run, which is fine.
                if display_count < 0 : # If it's -1, we are good.
                    break
                display_count = ctypes.windll.user32.ShowCursor(False)
                logger.debug(f"Called ShowCursor(False), new display count: {display_count}")

            logger.info(f"Cursor hidden. Final display count: {display_count}")
        except Exception as e:
            logger.error(f"Error calling ShowCursor(False): {e}", exc_info=True)
    else:
        logger.info("hide_cursor_completely is a Windows-specific function. Doing nothing on other OS.")


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')

    print("\n--- Testing get_active_window_title() ---")
    # Make sure to have a known window active when running this.
    # For example, your terminal or IDE.
    print("Please ensure this terminal/IDE window is active for the next 5 seconds.")
    time.sleep(5)
    active_title = get_active_window_title()
    if active_title:
        print(f"Active window title: '{active_title}'")
    else:
        print("Could not get active window title or no title found.")

    if platform.system() == "Windows":
        print("\n--- Testing Cursor Visibility (Windows) ---")
        print("Attempting to hide cursor completely...")
        hide_cursor_completely()
        print("Cursor should be hidden now (if applicable and not overridden by OS).")
        print("Sleeping for 3 seconds...")
        time.sleep(3)

        print("Attempting to show cursor until visible...")
        show_cursor_until_visible()
        print("Cursor should be visible now.")
        print("Sleeping for 3 seconds...")
        time.sleep(3)

        print("\n--- Second hide/show test ---")
        # Test to see if repeated calls work as expected
        # Show it multiple times (increases counter)
        print("Showing cursor a few more times to increment counter...")
        show_cursor_until_visible()
        show_cursor_until_visible() # Counter should be positive now

        print("Hiding cursor again...")
        hide_cursor_completely()
        print("Cursor should be hidden.")
        time.sleep(2)
        print("Showing cursor finally.")
        show_cursor_until_visible()
        print("Cursor should be visible.")

    else:
        print("\n--- Cursor Visibility Tests ---")
        print("Cursor visibility functions are Windows-specific. Skipping direct tests on this OS.")
        # Still call them to ensure they don't crash on other OS
        hide_cursor_completely()
        show_cursor_until_visible()

    print("\nWindow utils test finished.")
