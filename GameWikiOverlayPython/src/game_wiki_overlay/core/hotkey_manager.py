import threading
import logging
from pynput import keyboard

# For potential Qt signal emission if callbacks need UI interaction (not used directly in this version)
# from PyQt6.QtCore import QObject, pyqtSignal

try:
    from ..common.data_models import HotkeyConfig
except ImportError:
    # Fallback for direct execution (testing)
    logging.warning("Could not import HotkeyConfig from ..common.data_models. Using placeholder.")
    class HotkeyConfig:
        def __init__(self, Key="F1", Modifiers=None):
            self.Key = Key
            self.Modifiers = Modifiers if Modifiers is not None else ["Ctrl"]

logger = logging.getLogger(__name__)

class HotkeyManager:
    # If using Qt signals for thread-safe UI updates from callback:
    # class HotkeyManager(QObject):
    #     hotkey_pressed_signal = pyqtSignal()
    #
    #     def __init__(self, on_hotkey_pressed_callback=None, parent=None):
    #         super().__init__(parent)
    #         self.hotkey_pressed_signal.connect(on_hotkey_pressed_callback)
    # else:
    def __init__(self, on_hotkey_pressed_callback=None):
        self.on_hotkey_pressed_callback = on_hotkey_pressed_callback
        self.listener: keyboard.Listener = None
        self.current_hotkey_config: HotkeyConfig = None
        self.hotkey_active = False
        self._lock = threading.Lock() # To protect listener start/stop operations

        # Basic logging setup if not configured globally
        if not logger.hasHandlers():
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s')

    def _parse_hotkey(self, hotkey_config: HotkeyConfig) -> str:
        """
        Converts HotkeyConfig into a string format suitable for pynput.keyboard.HotKey.parse().
        Example: Modifiers = ["Ctrl", "Shift"], Key = "F1" -> "<ctrl>+<shift>+<f1>"
        """
        if not hotkey_config:
            return None

        parts = []
        # Modifier mapping: UI names to pynput names
        modifier_map = {
            "Ctrl": "ctrl",
            "Shift": "shift",
            "Alt": "alt",
            "Win": "cmd",  # 'cmd' is often used for Windows/Super key in pynput for cross-platform feel
                           # (especially with Mac where it's Command). 'super' is also an option.
                           # pynput might alias 'win' to 'cmd' or 'super' depending on platform.
        }
        for mod in hotkey_config.Modifiers:
            pynput_mod = modifier_map.get(mod)
            if pynput_mod:
                parts.append(f"<{pynput_mod}>")
            else:
                logger.warning(f"Unknown modifier: {mod}")

        # Key mapping
        key_lower = hotkey_config.Key.lower()

        # Check if it's an F-key (f1-f12)
        is_f_key = key_lower.startswith("f") and key_lower[1:].isdigit() and 1 <= int(key_lower[1:]) <= 12

        if is_f_key:
            parts.append(f"<{key_lower}>")  # e.g., <f1>, <f12>
        elif len(key_lower) > 1:  # Other multi-character named keys
            parts.append(f"<{key_lower}>")  # e.g., <space>, <enter>, <home>, <left>
        else:  # Single character keys
            parts.append(key_lower)  # e.g., a, 1, ;

        parsed_string = "+".join(parts)
        logger.debug(f"Parsed hotkey string: {parsed_string} from Modifiers={hotkey_config.Modifiers}, Key={hotkey_config.Key}")
        return parsed_string

    def _on_press_internal(self):
        logger.info(f"Hotkey {self.current_hotkey_config.Key if self.current_hotkey_config else 'Unknown'} pressed!")
        if self.on_hotkey_pressed_callback:
            try:
                # If using Qt signals for UI interaction:
                # self.hotkey_pressed_signal.emit()
                self.on_hotkey_pressed_callback()
            except Exception as e:
                logger.error(f"Error in on_hotkey_pressed_callback: {e}", exc_info=True)

    def register_global_hotkey(self, hotkey_config: HotkeyConfig, on_hotkey_pressed_callback=None):
        with self._lock:
            if on_hotkey_pressed_callback:
                self.on_hotkey_pressed_callback = on_hotkey_pressed_callback

            if not hotkey_config or not hotkey_config.Key:
                logger.error("Cannot register hotkey: Invalid HotkeyConfig provided.")
                return False

            self.current_hotkey_config = hotkey_config
            parsed_hotkey_str = self._parse_hotkey(hotkey_config)

            if not parsed_hotkey_str:
                logger.error("Failed to parse hotkey configuration.")
                return False

            if self.listener:
                logger.info("Stopping existing listener before registering new hotkey.")
                self._stop_listener_internal() # Use internal stop to avoid re-acquiring lock

            try:
                # Using pynput.keyboard.GlobalHotKeys for robust named hotkey registration
                # The format for GlobalHotKeys is {'<ctrl>+<alt>+h': on_activate, ...}
                hotkey_actions = {
                    parsed_hotkey_str: self._on_press_internal
                }
                self.listener = keyboard.GlobalHotKeys(hotkey_actions)
                self.listener.start()
                self.hotkey_active = True
                logger.info(f"Global hotkey '{parsed_hotkey_str}' registered successfully.")
                return True
            except Exception as e:
                logger.error(f"Failed to register global hotkey '{parsed_hotkey_str}': {e}", exc_info=True)
                self.current_hotkey_config = None # Clear if registration failed
                if self.listener: # Ensure listener is stopped if it failed mid-start or during parsing
                    self._stop_listener_internal() # self.listener might not be fully formed or started
                return False


    def _stop_listener_internal(self):
        """Internal method to stop listener, assumes lock is already held."""
        if self.listener:
            try:
                self.listener.stop()
                # GlobalHotKeys listener thread might not need explicit join if stop is sufficient
                # and it daemonizes its thread or handles join internally.
                # If it's a plain keyboard.Listener, join is good practice.
                if hasattr(self.listener, 'join') and callable(self.listener.join):
                    self.listener.join(timeout=1) # Add timeout to prevent indefinite block
            except Exception as e:
                logger.error(f"Error stopping listener: {e}", exc_info=True)
            finally:
                self.listener = None
        self.hotkey_active = False


    def unregister_global_hotkey(self):
        with self._lock:
            self._stop_listener_internal()
        logger.info("Global hotkey unregistered.")

    def reregister_hotkeys(self, hotkey_config: HotkeyConfig, on_hotkey_pressed_callback=None) -> bool:
        logger.info(f"Reregistering hotkeys for: {hotkey_config.Key} + {hotkey_config.Modifiers}")
        # unregister_global_hotkey already acquires lock
        self.unregister_global_hotkey()
        # register_global_hotkey also acquires lock
        return self.register_global_hotkey(hotkey_config, on_hotkey_pressed_callback)

    def stop_listener_if_running(self):
        """Utility function to ensure listener is stopped, typically on application exit."""
        logger.info("HotkeyManager stopping listener if running...")
        self.unregister_global_hotkey()


if __name__ == '__main__':
    # Setup basic logging for the test
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(levelname)s] %(name)s (%(threadName)s): %(message)s')

    main_stop_event = threading.Event()

    def my_hotkey_callback():
        print(">>> Hotkey Pressed! (Callback Executed) <<<")
        # Example: if you want to stop after first press for testing a sequence
        # print("Signaling main thread to stop after this activation.")
        # main_stop_event.set()


    hotkey_manager = HotkeyManager(on_hotkey_pressed_callback=my_hotkey_callback)

    # Test 1: Register Ctrl+Shift+F1
    print("\n--- Test 1: Registering Ctrl+Shift+F1 ---")
    config1 = HotkeyConfig(Key="F1", Modifiers=["Ctrl", "Shift"])
    if hotkey_manager.register_global_hotkey(config1):
        print(f"Hotkey {config1.Modifiers}+{config1.Key} registered. Try pressing it.")
        print("Input 'next' to proceed to the next test, or 'exit' to quit.")
        while True:
            cmd = input("> ").strip().lower()
            if cmd == 'next':
                break
            elif cmd == 'exit':
                main_stop_event.set()
                break
            if main_stop_event.is_set(): break # If callback set it
    else:
        print(f"Failed to register {config1.Modifiers}+{config1.Key}.")

    if main_stop_event.is_set():
        hotkey_manager.stop_listener_if_running()
        print("Exiting test early.")
        import sys # Make sure sys is imported for sys.exit()
        sys.exit()

    # Test 2: Reregister with Alt+S
    print("\n--- Test 2: Reregistering with Alt+S ---")
    config2 = HotkeyConfig(Key="S", Modifiers=["Alt"])

    def new_callback():
        print(">>> ALT+S Hotkey Pressed! (New Callback) <<<")

    if hotkey_manager.reregister_hotkeys(config2, new_callback):
        print(f"Hotkey {config2.Modifiers}+{config2.Key} registered. Ctrl+Shift+F1 should be inactive. Try pressing Alt+S.")
        print("Input 'next' to proceed to unregister test, or 'exit' to quit.")
        while True:
            cmd = input("> ").strip().lower()
            if cmd == 'next':
                break
            elif cmd == 'exit':
                main_stop_event.set()
                break
    else:
        print(f"Failed to re-register {config2.Modifiers}+{config2.Key}.")


    if main_stop_event.is_set():
        hotkey_manager.stop_listener_if_running()
        print("Exiting test early.")
        import sys # Make sure sys is imported for sys.exit()
        sys.exit()

    # Test 3: Unregister
    print("\n--- Test 3: Unregistering Hotkey ---")
    hotkey_manager.unregister_global_hotkey()
    print(f"Hotkeys unregistered. Alt+S should no longer work.")
    print("Input 'exit' to quit.")
    while not main_stop_event.is_set():
        cmd = input("> ").strip().lower()
        if cmd == 'exit':
            break

    hotkey_manager.stop_listener_if_running() # Ensure cleanup
    print("\nHotkeyManager test finished.")

    # Note: pynput listener threads might take a moment to fully terminate.
    # If issues with script not exiting, ensure listener.join() is effective or listener thread is daemon.
    # GlobalHotKeys uses daemon threads by default, so they should not block exit.
