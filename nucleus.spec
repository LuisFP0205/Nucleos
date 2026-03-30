# nucleus.spec
# Gera um executável em pasta (--onedir) com pywebview.
#
# Como buildar:
#   pip install pyinstaller
#   pyinstaller nucleus.spec

from PyInstaller.utils.hooks import collect_all

curl_datas, curl_binaries, curl_hiddenimports = collect_all("curl_cffi")
wv_datas, wv_binaries, wv_hiddenimports = collect_all("webview")
cffi_datas, cffi_binaries, cffi_hiddenimports = collect_all("cffi")
pn_datas, pn_binaries, pn_hiddenimports = collect_all("pythonnet")
clr_datas, clr_binaries, clr_hiddenimports = collect_all("clr_loader")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[*curl_binaries, *wv_binaries, *cffi_binaries, *pn_binaries, *clr_binaries],
    datas=[
        ("static",   "static"),
        ("overlays", "overlays"),
        ("Icones",   "Icones"),
        *curl_datas,
        *wv_datas,
        *cffi_datas,
        *pn_datas,
        *clr_datas,
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "winsdk.windows.media.control",
        "winsdk.windows.storage.streams",
        "websockets.asyncio.client",
        "websockets.legacy.client",
        "pydantic_settings",
        "webview.platforms.winforms",
        "clr",
        *wv_hiddenimports,
        *curl_hiddenimports,
        "_cffi_backend",
        *cffi_hiddenimports,
        *pn_hiddenimports,
        *clr_hiddenimports,
    ],
    hookspath=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nucleus",
    icon="Icones/nucleus.ico",
    console=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Nucleus",
)
