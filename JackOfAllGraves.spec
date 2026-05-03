# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Jack of All Graves
# Build with: pyinstaller JackOfAllGraves.spec --clean
# Output: dist/JackOfAllGraves/ folder — share the whole folder.
# Requires PyInstaller >= 6.0

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['jack/server.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Web UI
        ('jack/index.html',   'jack'),
        ('jack/css',          'jack/css'),
        ('jack/js',           'jack/js'),
        # Game data (JSON, CSV, map images)
        ('jack/data',         'jack/data'),
        # Confirmed release model
        ('jack/rl/models/bingo_agent.zip', 'jack/rl/models'),
        # Package data files (version.txt etc.)
        *collect_data_files('stable_baselines3'),
        *collect_data_files('sb3_contrib'),
        *collect_data_files('gymnasium'),
    ],
    hiddenimports=[
        # RL stack
        'sb3_contrib',
        'sb3_contrib.ppo_mask',
        'sb3_contrib.common',
        'sb3_contrib.common.maskable',
        'sb3_contrib.common.maskable.policies',
        'sb3_contrib.common.maskable.utils',
        'sb3_contrib.common.maskable.evaluation',
        'stable_baselines3',
        'stable_baselines3.common',
        'stable_baselines3.common.policies',
        'stable_baselines3.common.torch_layers',
        'stable_baselines3.common.utils',
        'gymnasium',
        'gymnasium.spaces',
        'numpy',
        'torch',
        # Project modules
        'jack',
        'jack.rl',
        'jack.rl.agent',
        'jack.rl.board',
        'jack.rl.constants',
        'jack.rl.env',
        'jack.rl.sim',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JackOfAllGraves',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='JackOfAllGraves',
)
