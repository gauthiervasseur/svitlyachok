# Third-party software

Світлячок is licensed under the GNU AGPL-3.0 (see `LICENSE`), because it bundles PyMuPDF, which is AGPL-3.0.
Its source code is available from the repository the app is downloaded from.

## Bundled in the app

| Component | Licence | Used for |
|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) 1.28 | AGPL-3.0 (or Artifex commercial) | Reading and rendering PDFs |
| [pymupdf4llm](https://github.com/pymupdf/pymupdf4llm) 0.3 | AGPL-3.0 (or Artifex commercial) | PDF text layer → Markdown |
| [MLX](https://github.com/ml-explore/mlx), [mlx-vlm](https://github.com/Blaizzy/mlx-vlm) (Mac) | MIT | OCR engine on Apple Silicon |
| [PyTorch](https://pytorch.org/), torchvision (Windows) | BSD-3-Clause | OCR engine on Windows |
| [Transformers](https://github.com/huggingface/transformers), huggingface_hub | Apache-2.0 | Model loading and download |
| [pywebview](https://pywebview.flowrl.com/) | BSD-3-Clause | Native window |
| mammoth / markdownify / python-pptx / openpyxl | BSD-2 / MIT / MIT / MIT | Word, PowerPoint, Excel files |
| Pillow, pillow-heif | MIT-CMU, BSD-3-Clause (bundles libheif, LGPL-3.0) | Images, iPhone HEIC photos |
| einops, addict, easydict, tabulate, numpy | MIT, MIT, LGPL-3.0, MIT, BSD-3-Clause | Model code and tables |
| [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) font | SIL Open Font License 1.1 | Interface font |

## Downloaded on first use (not bundled)

| Model | Licence |
|---|---|
| [baidu/Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR) (Windows) | MIT |
| [mlx-community/Unlimited-OCR-bf16](https://huggingface.co/mlx-community/Unlimited-OCR-bf16) (Mac, MLX conversion of the same weights) | MIT |

`pymupdf-layout` (PolyForm Noncommercial) is deliberately **not** used, which is why PyMuPDF is pinned to 1.x.
