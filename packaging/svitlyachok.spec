# PyInstaller spec for both platforms:  pyinstaller packaging/svitlyachok.spec
#   macOS (Apple Silicon): Svitlyachok.app with the MLX engine
#   Windows:               Svitlyachok/ folder with Svitlyachok.exe and the PyTorch (CPU) engine
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from svitlyachok import __version__  # noqa: E402

import os  # noqa: E402

# SVITLYACHOK_ENGINE=torch builds the Windows (PyTorch) variant on a Mac, to test its packaging locally.
IS_MAC = sys.platform == "darwin" and os.environ.get("SVITLYACHOK_ENGINE") != "torch"

datas = [
    (str(ROOT / "svitlyachok" / "ui"), "svitlyachok/ui"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE.md"), "."),
]
binaries = []
hiddenimports = collect_submodules("svitlyachok")


def bundle(package):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas.extend(pkg_datas)
    binaries.extend(pkg_binaries)
    hiddenimports.extend(pkg_hidden)


for package in ("pymupdf", "pymupdf4llm"):
    bundle(package)
hiddenimports += ["mammoth", "markdownify", "pptx", "openpyxl", "pillow_heif"]
datas += collect_data_files("pptx") + collect_data_files("mammoth")

if IS_MAC:
    bundle("mlx")  # native library and Metal shader library (mlx.metallib)
    datas += collect_data_files("mlx_vlm")
    # mlx_vlm imports the model module by name from config.json, so static analysis misses it.
    hiddenimports += collect_submodules("mlx_vlm.models.unlimited_ocr") + collect_submodules("mlx_vlm.models.deepseekocr")
    excludes = ["torch", "torchvision", "tkinter", "matplotlib", "IPython", "pytest", "pymupdf.layout", "onnxruntime"]
else:
    # Imported at runtime by the model's own code (trust_remote_code), invisible to static analysis.
    hiddenimports += ["addict", "easydict", "einops", "requests", "matplotlib.pyplot", "torchvision.transforms"]
    # transformers imports model and tokenizer modules by name at runtime, so bundle all of them.
    hiddenimports += collect_submodules("transformers")
    datas += collect_data_files("transformers", include_py_files=False)
    excludes = ["mlx", "mlx_vlm", "tkinter", "IPython", "pytest", "pymupdf.layout", "onnxruntime"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Svitlyachok",
    console=False,
    icon=str(ROOT / "assets" / ("icon.icns" if IS_MAC else "icon.ico")),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Svitlyachok", upx=False)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Svitlyachok.app",
        icon=str(ROOT / "assets" / "icon.icns"),
        bundle_identifier="academy.datawise.svitlyachok",
        version=__version__,
        info_plist={
            "CFBundleName": "Світлячок",
            "CFBundleDisplayName": "Світлячок",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "14.0",
            "LSArchitecturePriority": ["arm64"],
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Світлячок · OCR by Baidu Unlimited-OCR (MIT)",
        },
    )
