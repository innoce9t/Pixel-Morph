# PixelMorph

A small desktop GUI for bulk file conversion: turn PDFs into images, and convert images between formats. Drag files in, pick a format, convert.

## Features

- **PDF → image** — render every page of a PDF at a chosen DPI
- **Image → image** — convert between JPG, PNG, and WEBP
- **Batch** — queue many files at once; conversion runs on a worker thread so the UI stays responsive
- **Drag and drop** — supported when `tkinterdnd2` is installed (falls back to a file picker if not)
- **Combine pages** — optionally stitch a multi-page PDF into a single image
- **Per-PDF subfolders** — optionally give each source PDF its own output folder
- **Skip existing** — don't re-convert files that already exist in the output folder
- **Alpha handling** — RGBA/LA/P images are flattened onto white when saving as JPG
- **Remembered settings** — preferences persist in `pixelmorph_config.json`

Accepted inputs: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`, `.gif`
Output formats: `JPG`, `PNG`, `WEBP`

## Requirements

- Python 3.10+ with Tkinter
- Dependencies from `requirements.txt`:
  - [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF rendering
  - [Pillow](https://python-pillow.org/) — image conversion
  - [tkinterdnd2](https://pypi.org/project/tkinterdnd2/) — drag and drop (optional)

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python pixelmorph.py
```

On Windows, `Run.bat` does the same and keeps the console open if it errors.

## Configuration

Settings are saved to `pixelmorph_config.json` next to the script:

| Key | Meaning |
|---|---|
| `output_dir` | Where converted files are written |
| `output_format` | `JPG`, `PNG`, or `WEBP` |
| `dpi` | Render resolution for PDF pages |
| `quality` | JPG/WEBP quality, 1–100 |
| `combine_pages` | Merge a PDF's pages into one image |
| `subfolder_per_pdf` | Give each PDF its own output folder |
| `skip_existing` | Skip files already present in the output folder |

Delete the file to reset to defaults.

## Files

```
pixelmorph.py            Application (GUI + conversion logic)
make_icon.py             Generates pixelmorph.ico
requirements.txt         Python dependencies
Run.bat                  Windows launcher
pixelmorph_config.json   Saved settings
```
