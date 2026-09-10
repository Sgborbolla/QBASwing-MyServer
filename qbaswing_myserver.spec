# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller para "QBASwing MyServer.exe"
#
# Uso (ejecutar en Windows, dentro de la carpeta del proyecto, con el venv activado):
#
#   pip install pyinstaller
#   pyinstaller qbaswing_myserver.spec
#
# El ejecutable final aparece en dist/QBASwing MyServer/QBASwing MyServer.exe

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('frontend/templates', 'frontend/templates'),
        ('frontend/static', 'frontend/static'),
        ('translations', 'translations'),
        ('database/schema.sql', 'database'),
    ],
    hiddenimports=['backend.db', 'backend.scanner', 'backend.pricing', 'backend.network',
                    'backend.auth', 'backend.i18n', 'backend.device'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QBASwing MyServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,      # deja la consola visible (util para ver la IP local del servidor)
    icon=None,          # coloca aqui la ruta a un .ico (puedes generarlo desde el logo)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QBASwing MyServer',
)
