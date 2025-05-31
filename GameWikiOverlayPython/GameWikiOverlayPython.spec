# GameWikiOverlayPython.spec
# -*- mode: python ; coding: utf-8 -*-

# When running PyInstaller, it's typically run from the project root where this spec file is located.
# The paths in this spec file are relative to the location of the spec file.

block_cipher = None

# Correct pathex should be relative to the spec file location.
# If main.py is 'src/game_wiki_overlay/main.py', and spec file is in project root,
# then 'src' is a directory at the same level as the files/dirs referenced in Analysis.
# PyInstaller adds the directory of the spec file to sys.path by default.
# pathex=['src'] tells PyInstaller to also add the 'src' subdirectory to its search path for modules.
# This helps if main.py or its dependencies use imports assuming 'src' is a root for them.
# For `from game_wiki_overlay.app_logic import AppLogic` inside `src/game_wiki_overlay/main.py` (using `from .app_logic`),
# PyInstaller usually handles this well if the main script is `src/game_wiki_overlay/main.py`.
# `pathex=['src']` is good practice if your project structure within `src` is complex or uses direct imports like `import game_wiki_overlay`.

a = Analysis(
    ['src/game_wiki_overlay/main.py'], # Path to the main script relative to this spec file
    pathex=['src'],                    # Add 'src' to module search path
    binaries=[],
    datas=[
        # (source_path_on_disk, destination_in_bundle_relative_to_dist_root)
        ('src/game_wiki_overlay/ui/assets/app.png', 'game_wiki_overlay/ui/assets'),
        ('data_defaults/games.json', 'data_defaults'),
        ('data_defaults/settings.json', 'data_defaults')
    ],
    hiddenimports=[
        'pystray._win32',
        'pystray._appindicator', # For Linux AppIndicator support with pystray
        'pystray._xorg',         # For Linux Xorg support with pystray
        'pygetwindow._pygetwindow_win',
        'pygetwindow._pygetwindow_x11',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pynput.keyboard._xorg', # For Linux Xorg support with pynput
        'pynput.mouse._xorg',    # For Linux Xorg support with pynput
        # PyQt6 WebEngine hidden imports are usually handled by PyQt6 hooks,
        # but if issues arise, specific modules like 'PyQt6.QtWebEngineCore',
        # 'PyQt6.QtWebEngineWidgets.WebEngineViewRenderer' might be needed.
        'pkg_resources.py2_warn', # Common, for packages that might still use pkg_resources
        'PIL.Image',              # Ensure Pillow's Image module is included
        'PIL.PngImagePlugin',     # Specifically for PNG if not picked up
        'appdirs',
        'tkinter',                # Used for fallback error GUI in main.py
        'importlib_metadata',     # Sometimes needed by other packages like appdirs
        'packaging.version',      # Dependency for some libraries
        'packaging.specifiers',
        'packaging.requirements',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# PyQt6 specific configurations:
# PyInstaller's built-in hooks for PyQt6 are generally good.
# If QtWebEngine resources (like .pak files, locales, WebEngineProcess) are missing
# in the bundled app, you might need to explicitly collect them.
# Example of collecting Qt plugins (often handled by hooks, but good to know):
# from PyInstaller.utils.hooks import copy_qt_plugins
# copy_qt_plugins(a, ['platforms', 'styles', 'iconengines', 'imageformats', 'webenginewidgets', 'tls'])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [], # a.binaries are usually handled by Analysis, keep this empty unless specific needs
    a.zipfiles,
    a.datas, # a.datas is already prepared by Analysis
    name='GameWikiOverlayPython',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True, # UPX compression (ensure UPX is installed and in PATH if True)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # True for console app, False for windowed (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None, # None for auto-detect, or specify e.g. 'x86_64'
    codesign_identity=None,
    entitlements_file=None,
    icon='src/game_wiki_overlay/ui/assets/app.ico' # Path to app icon (for .exe on Windows, .app on macOS)
)

# For macOS .app bundle, an Info.plist can be specified:
# app_bundle = BUNDLE(exe,
#             name='GameWikiOverlayPython.app',
#             icon='src/game_wiki_overlay/ui/assets/app.icns', # .icns for macOS
#             bundle_identifier='com.yourdomain.gamewikioverlaypython',
#             info_plist={
#                 'NSHighResolutionCapable': 'True',
#                 'NSPrincipalClass': 'NSApplication', # If using AppKit directly (not typical for PyQt)
#                 'NSRequiresAquaSystemAppearance': 'No', # For dark mode support etc.
#                 'CFBundlePackageType': 'APPL',
#                 # Add other keys as needed
#             })
# This BUNDLE part is only for macOS. For Windows/Linux, EXE is the final target.
# If you want a single spec for multi-platform, you can use platform checks:
# if sys.platform == 'darwin':
#     coll = BUNDLE(...)
# else:
#     coll = COLLECT(...) # COLLECT is used for onedir mode if not just an EXE
# For onedir mode (default if not --onefile):
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GameWikiOverlayPython' # This will be the output folder name in 'dist'
)
