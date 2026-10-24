# Світлячок (Svitlyachok)

A Mac and Windows app that turns documents into Markdown: drop PDFs, scans, photos, Word, Excel or
PowerPoint files, then save the results as `.md`. Scanned pages are read by Baidu's
[Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR); digital files are converted directly.
Everything runs locally.

- **Mac (Apple Silicon, macOS 14+):** OCR on the GPU with MLX, ~5 s per scanned page.
- **Windows 10/11 (64-bit):** OCR on the CPU with PyTorch, minutes per scanned page.
- **Both:** digital PDFs and Office files convert in under a second.

The download page for the team is in `website/`, published by GitHub Pages.

## Layout

| Path | What |
|---|---|
| `svitlyachok/app.py` | Window, queue and the API called from the UI |
| `svitlyachok/ui/` | The 80s arcade interface (HTML/CSS/JS). Open `index.html?mock` in a browser to preview it with fake data |
| `svitlyachok/engine/core.py` | Routing (Office/text → direct, PDF text layer → direct, scans → OCR) and model output → Markdown |
| `svitlyachok/engine/backend_mlx.py`, `backend_torch.py` | The two OCR engines (the PyTorch one carries fixes for Apple's MPS) |
| `svitlyachok/engine/formats.py` | DOCX, PPTX, XLSX, CSV, HTML, text and code files |
| `svitlyachok/engine/weights.py` | First-run model download with progress |
| `svitlyachok/selftest.py` | Headless checks: `Svitlyachok --selftest [--ocr]` |
| `packaging/` | PyInstaller spec, Mac build script, Windows installer (Inno Setup) |
| `website/` | Download page |
| `.github/workflows/` | `release.yml` builds both apps on a tag; `pages.yml` publishes the website |

## Run from source (Mac)

```bash
uv venv --python 3.12 ~/.venvs/svitlyachok-mac
VIRTUAL_ENV=~/.venvs/svitlyachok-mac uv pip install -r requirements-mac.txt
~/.venvs/svitlyachok-mac/bin/python -m svitlyachok
```

Set `SVITLYACHOK_DEBUG=1` to get the web inspector. The log is in
`~/Library/Application Support/Svitlyachok/svitlyachok.log`, or `%LOCALAPPDATA%\Svitlyachok` on Windows.

## Build the Mac app locally

```bash
VIRTUAL_ENV=~/.venvs/svitlyachok-mac uv pip install pyinstaller==6.22.3
python3 packaging/mlx_wheels.py /tmp/mlx-wheels    # macOS 14 builds of MLX, for older Macs
VIRTUAL_ENV=~/.venvs/svitlyachok-mac uv pip install --reinstall --no-deps /tmp/mlx-wheels/*.whl
PATH=~/.venvs/svitlyachok-mac/bin:$PATH packaging/build-mac.sh ~/Builds/svitlyachok
```

Keep build output outside this synced folder. The Windows app can only be built on Windows,
which GitHub Actions does.

## Release

1. Bump `__version__` in `svitlyachok/__init__.py` and commit.
2. Tag and push: `git tag v1.0.1 && git push origin main v1.0.1`.
3. GitHub Actions builds and self-tests both apps (on Windows this includes a real OCR test), then
   publishes a Release with `Svitlyachok-macOS.dmg` and `Svitlyachok-Windows-Setup.exe`. The
   website always links to the latest release.

To build without releasing, run **Build & release** manually from the Actions tab. The installers
appear as workflow artifacts.

### One-time GitHub setup

- Create the repository `svitlyachok`. If you use another name, update `REPO` in
  `website/script.js`.
- **Settings → Pages → Source: GitHub Actions** turns on the website.
- Visibility: with a **public** repo, anyone with the link can download, and the AGPL source
  requirement is met automatically. With a **private** repo, each teammate needs a GitHub account
  with access, and GitHub Pages needs a paid plan.

## Not signed yet

The apps are not signed with an Apple Developer ID or a Windows code-signing certificate, so the
first launch needs one extra click. The website explains how. Signing and notarising (Apple
Developer Program, $99/year) would remove that step. It can be added to `release.yml` later.

## Licence

AGPL-3.0, because the app bundles PyMuPDF (AGPL-3.0). See `NOTICE.md` for all components.
PyMuPDF is pinned to 1.x: 2.x requires `pymupdf-layout`, which is PolyForm Noncommercial.
