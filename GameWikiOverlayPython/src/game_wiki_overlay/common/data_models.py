from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field

class GameConfig(BaseModel):
    BaseUrl: str
    NeedsSearch: bool = True
    SearchTemplate: Optional[str] = None
    KeywordMap: Optional[Dict[str, str]] = None

class HotkeyConfig(BaseModel):
    Key: str
    Modifiers: List[str] = Field(default_factory=list)

class PopupConfig(BaseModel):
    Width: float = 800.0
    Height: float = 600.0
    Left: float = 100.0
    Top: float = 100.0

class AppSettings(BaseModel):
    Hotkey: HotkeyConfig
    Popup: PopupConfig

# Example of a more complex GameConfigs structure if games.json stores a dictionary of GameConfig
# For now, we assume games.json will be Dict[str, GameConfig] and loaded directly.
# If games.json had a top-level key, e.g., {"games": {"game_name": {...}}},
# then a GameConfigs model would be useful here.
