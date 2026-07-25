
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'requests', 'urllib3', 'certifi',
        'optparse'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # === QtWebEngine (Chromium) — ~100-130 МБ, не нужен ===
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel', 'PySide6.QtWebEngine',
        # === yt-dlp — скачивается при первом запуске, не включаем в сборку ===
        'yt_dlp', 'yt_dlp.utils', 'yt_dlp.extractor', 'yt_dlp.postprocessor',
        'Cryptodome', 'websockets', 'mutagen', 'brotli', 'curl_cffi',
        # === Неиспользуемые модули PySide6/Qt6 — экономия ~50-80 МБ ===
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic', 'PySide6.Qt3DExtras', 'PySide6.Qt3DAnimation',
        'PySide6.Qt3DQuickCore', 'PySide6.Qt3DQuickRender', 'PySide6.Qt3DQuickInput',
        'PySide6.Qt3DQuickExtras', 'PySide6.Qt3DQuickAnimation', 'PySide6.Qt3DQuickLogic',
        'PySide6.Qt3DQuickScene3D',
        'PySide6.QtCharts', 'PySide6.QtChartsQml',
        'PySide6.QtDataVisualization',
        'PySide6.QtRemoteObjects', 'PySide6.QtRemoteObjectsQml',
        'PySide6.QtScxml',
        'PySide6.QtStateMachine',
        'PySide6.QtTest',
        'PySide6.QtQuick3D', 'PySide6.QtQuick3DHelpers', 'PySide6.QtQuick3DHelpersImpl',
        'PySide6.QtQuick3DRuntimeRender', 'PySide6.QtQuick3DAssetImport',
        'PySide6.QtSensors',
        'PySide6.QtSql',
        'PySide6.QtSpatialAudio',
        'PySide6.QtLabsWavefrontMesh', 'PySide6.QtLabsSharedImage',
        'PySide6.QtQuickVectorImageGenerator',
        'PySide6.QtSerialPort',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebView',
        'PySide6.QtVirtualKeyboard',
        'PySide6.QtNetworkAuth',
        'PySide6.QtConcurrent',
        'PySide6.QtOpenGLWidgets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VideoCompressor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
