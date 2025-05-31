import json
import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Union

import appdirs
from pydantic import ValidationError

from .common.data_models import AppSettings, GameConfig, HotkeyConfig, PopupConfig

APP_NAME = "GameWikiOverlayPython"
APP_AUTHOR = "GameWikiOverlay"  # Using a generic author name

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.user_config_dir: Path = Path(appdirs.user_config_dir(APP_NAME, APP_AUTHOR))
        self.user_settings_path: Path = self.user_config_dir / "settings.json"
        self.user_games_config_path: Path = self.user_config_dir / "games.json" # User overrides for games

        # Default configs are shipped with the application
        # Assuming this file is in src/game_wiki_overlay, so ../../.. goes to project root
        project_root = Path(__file__).resolve().parent.parent.parent
        self.default_settings_path: Path = project_root / "data_defaults" / "settings.json"
        self.default_games_config_path: Path = project_root / "data_defaults" / "games.json"

        self._ensure_config_dir_exists()

    def _ensure_config_dir_exists(self):
        """Ensures the user-specific configuration directory exists."""
        if not self.user_config_dir.exists():
            try:
                os.makedirs(self.user_config_dir, exist_ok=True)
                logger.info(f"Created user config directory: {self.user_config_dir}")
            except OSError as e:
                logger.error(f"Error creating user config directory {self.user_config_dir}: {e}", exc_info=True)
                # Propagate or handle as critical failure if necessary
                raise

    def _get_default_hotkey_config(self) -> HotkeyConfig:
        return HotkeyConfig(Key="F1", Modifiers=["Ctrl"])

    def _get_default_popup_config(self) -> PopupConfig:
        return PopupConfig()

    def load_settings(self) -> AppSettings:
        """Loads application settings from user's config, falling back to defaults."""
        if not self.user_settings_path.exists():
            logger.info(f"User settings file not found at {self.user_settings_path}. Attempting to use defaults.")
            if self.default_settings_path.exists():
                try:
                    shutil.copy(self.default_settings_path, self.user_settings_path)
                    logger.info(f"Copied default settings to {self.user_settings_path}")
                except IOError as e:
                    logger.error(f"Error copying default settings from {self.default_settings_path} to {self.user_settings_path}: {e}", exc_info=True)
                    # Fallback to creating settings programmatically if copy fails
                    default_settings = AppSettings(
                        Hotkey=self._get_default_hotkey_config(),
                        Popup=self._get_default_popup_config()
                    )
                    self.save_settings(default_settings)
                    return default_settings
            else:
                logger.warning(f"Default settings file not found at {self.default_settings_path}. Creating new default settings.")
                default_settings = AppSettings(
                    Hotkey=self._get_default_hotkey_config(),
                    Popup=self._get_default_popup_config()
                )
                self.save_settings(default_settings) # Save it for future loads
                return default_settings

        try:
            with open(self.user_settings_path, 'r') as f:
                data = json.load(f)
            return AppSettings(**data)
        except FileNotFoundError: # Should be caught by earlier checks, but as a safeguard
            logger.error(f"Settings file {self.user_settings_path} not found despite earlier checks.", exc_info=True)
            # This case implies a race condition or an issue with the initial copy/creation logic
            default_settings = AppSettings(Hotkey=self._get_default_hotkey_config(), Popup=self._get_default_popup_config())
            self.save_settings(default_settings)
            return default_settings
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from settings file {self.user_settings_path}: {e}", exc_info=True)
            # Fallback: try to load default settings, or create new if default also fails
            logger.info("Attempting to load/create fresh default settings due to JSON error.")
            # Potentially backup corrupted file before overwriting
            # For now, directly create and save new default settings
            default_settings = AppSettings(Hotkey=self._get_default_hotkey_config(), Popup=self._get_default_popup_config())
            self.save_settings(default_settings) # Overwrites potentially corrupted user file
            return default_settings
        except ValidationError as e:
            logger.error(f"Validation error for settings data in {self.user_settings_path}: {e}", exc_info=True)
            # Similar fallback strategy as JSONDecodeError
            default_settings = AppSettings(Hotkey=self._get_default_hotkey_config(), Popup=self._get_default_popup_config())
            self.save_settings(default_settings) # Overwrites potentially invalid user file
            return default_settings


    def save_settings(self, settings: AppSettings):
        """Saves application settings to the user's config directory."""
        self._ensure_config_dir_exists() # Ensure dir exists before writing
        try:
            with open(self.user_settings_path, 'w') as f:
                f.write(settings.model_dump_json(indent=4))
            logger.info(f"Settings saved to {self.user_settings_path}")
        except IOError as e:
            logger.error(f"Error saving settings to {self.user_settings_path}: {e}", exc_info=True)
        except ValidationError as e: # Should not happen if AppSettings instance is already validated
            logger.error(f"Validation error when trying to serialize settings: {e}", exc_info=True)


    def load_game_configs(self) -> Dict[str, GameConfig]:
        """
        Loads game configurations.
        Priority: User overrides > Default data.
        For simplicity, this version loads from default_games_config_path.
        A more advanced version would merge user_games_config_path with defaults.
        """
        source_path = self.default_games_config_path # Start with default path

        # Check if user-specific games.json exists and prefer it if so.
        # This example doesn't merge, but a real app might.
        # For now, we will just load the default one as per the instructions.
        # if self.user_games_config_path.exists():
        #     source_path = self.user_games_config_path
        #     logger.info(f"Loading game configs from user override: {source_path}")
        # elif not self.default_games_config_path.exists():
        #     logger.warning(f"Default game config file not found at {self.default_games_config_path}. Returning empty config.")
        #     return {}
        # else:
        # logger.info(f"Loading game configs from default: {source_path}")

        if not self.default_games_config_path.exists():
            logger.warning(f"Default game config file not found at {self.default_games_config_path}. Returning empty config.")
            # Optionally, copy from a bundled resource if this file is critical and might be missing
            return {}

        try:
            with open(self.default_games_config_path, 'r') as f:
                data = json.load(f)

            game_configs: Dict[str, GameConfig] = {}
            for game_name, config_data in data.items():
                try:
                    game_configs[game_name] = GameConfig(**config_data)
                except ValidationError as e:
                    logger.error(f"Validation error for game '{game_name}' in {self.default_games_config_path}: {e}", exc_info=True)
                    # Skip this game or handle error as appropriate
            logger.info(f"Successfully loaded {len(game_configs)} game configs from {self.default_games_config_path}")
            return game_configs
        except FileNotFoundError: # Should be caught by the exists check, but as a safeguard
            logger.error(f"Game config file {self.default_games_config_path} not found despite earlier checks.", exc_info=True)
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from game config file {self.default_games_config_path}: {e}", exc_info=True)
            return {}
        except Exception as e: # Catch any other unexpected errors during loading/parsing
            logger.error(f"An unexpected error occurred while loading game configs from {self.default_games_config_path}: {e}", exc_info=True)
            return {}

if __name__ == '__main__':
    # Basic logging setup for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Test ConfigManager
    manager = ConfigManager()

    # Test loading settings
    print("\n--- Loading Settings ---")
    settings = manager.load_settings()
    if settings:
        print(f"Loaded settings: Hotkey={settings.Hotkey.Key}+{settings.Hotkey.Modifiers}, Popup={settings.Popup.Width}x{settings.Popup.Height}")

        # Modify settings and save
        print("\n--- Modifying and Saving Settings ---")
        if settings.Hotkey.Key == "F1": # Avoid continuous modification in tests
            settings.Hotkey.Key = "F2"
            settings.Hotkey.Modifiers = ["Shift", "Ctrl"]
            settings.Popup.Width = 1024
        else:
            settings.Hotkey.Key = "F1"
            settings.Hotkey.Modifiers = ["Ctrl"]
            settings.Popup.Width = 800

        manager.save_settings(settings)
        print(f"Saved settings: Hotkey={settings.Hotkey.Key}+{settings.Hotkey.Modifiers}, Popup={settings.Popup.Width}x{settings.Popup.Height}")

        # Reload to verify
        print("\n--- Reloading Settings to Verify ---")
        reloaded_settings = manager.load_settings()
        if reloaded_settings:
            print(f"Reloaded settings: Hotkey={reloaded_settings.Hotkey.Key}+{reloaded_settings.Hotkey.Modifiers}, Popup={reloaded_settings.Popup.Width}x{reloaded_settings.Popup.Height}")
            assert reloaded_settings.Hotkey.Key == settings.Hotkey.Key
            assert reloaded_settings.Popup.Width == settings.Popup.Width

    # Test loading game configs
    print("\n--- Loading Game Configs ---")
    # To test this properly, ensure 'data_defaults/games.json' exists and has some content.
    # Example games.json:
    # {
    #   "ExampleGame": {
    #     "BaseUrl": "https://example.gamepedia.com/",
    #     "NeedsSearch": true,
    #     "SearchTemplate": "Special:Search?search={query}"
    #   }
    # }
    # For now, it will likely be empty unless you created and populated this file earlier.
    # If data_defaults/games.json is empty or malformed, this will show corresponding logs.

    # Create dummy games.json for testing if it doesn't exist
    default_games_json_path = manager.default_games_config_path
    if not default_games_json_path.exists():
        print(f"Creating dummy {default_games_json_path} for testing.")
        os.makedirs(default_games_json_path.parent, exist_ok=True)
        with open(default_games_json_path, 'w') as f:
            json.dump({
                "TestGame1": {"BaseUrl": "http://test1.wiki.com", "NeedsSearch": True, "SearchTemplate": "/search?q={query}"},
                "TestGame2": {"BaseUrl": "http://test2.fandom.com", "KeywordMap": {"boss": "Bosses", "item": "Items"}},
                "InvalidGame": {"BaseUrl": 123} # To test validation error
            }, f, indent=4)

    game_configs = manager.load_game_configs()
    if game_configs:
        for name, config in game_configs.items():
            print(f"Loaded game config for '{name}': BaseUrl={config.BaseUrl}, NeedsSearch={config.NeedsSearch}")
    else:
        print("No game configs loaded or an error occurred.")

    print("\n--- ConfigManager Test Complete ---")
    print(f"User config directory: {manager.user_config_dir}")
    print(f"User settings path: {manager.user_settings_path}")
    print(f"Default games config path: {manager.default_games_config_path}")
