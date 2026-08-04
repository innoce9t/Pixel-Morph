"""PixelMorph - bulk convert PDFs to images, and images between
formats (JPG/PNG/WEBP/etc), with a simple GUI."""

import json
import os
import threading
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import fitz  # PyMuPDF
from PIL import Image

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

APP_DIR = Path(__file__).resolve().parent

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS

FORMAT_TO_EXT = {"JPG": "jpg", "PNG": "png", "WEBP": "webp"}
FORMAT_TO_PIL = {"JPG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}

CONFIG_PATH = APP_DIR / "pixelmorph_config.json"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def save_pil_image(img, out_path, fmt, quality):
    """Save a PIL image to out_path in the given format (JPG/PNG/WEBP), handling alpha."""
    if fmt == "JPG":
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(out_path, format="JPEG", quality=quality)
    elif fmt == "WEBP":
        img.save(out_path, format="WEBP", quality=quality)
    else:  # PNG
        img.save(out_path, format="PNG")


class ConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("PixelMorph — PDF & Image Converter")
        root.geometry("760x620")
        root.minsize(680, 520)

        icon_path = APP_DIR / "pixelmorph.ico"
        if icon_path.exists():
            try:
                root.iconbitmap(str(icon_path))
            except Exception:
                pass

        cfg = load_config()

        self.files = []  # list of Path
        self.output_dir = tk.StringVar(value=cfg.get("output_dir", ""))
        self.dpi = tk.IntVar(value=cfg.get("dpi", 200))
        self.quality = tk.IntVar(value=cfg.get("quality", 90))
        self.subfolder_per_pdf = tk.BooleanVar(value=cfg.get("subfolder_per_pdf", True))
        self.combine_pages = tk.BooleanVar(value=cfg.get("combine_pages", False))
        self.skip_existing = tk.BooleanVar(value=cfg.get("skip_existing", True))
        self.output_format = tk.StringVar(value=cfg.get("output_format", "JPG"))

        self.cancel_requested = False
        self.worker_thread = None
        self.progress_queue = queue.Queue()

        self._build_ui()
        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", **pad)

        ttk.Button(top_frame, text="Add Files...", command=self.add_files).pack(side="left")
        ttk.Button(top_frame, text="Add Folder (with subfolders)...", command=self.add_folder).pack(side="left", padx=(8, 0))
        ttk.Button(top_frame, text="Clear List", command=self.clear_files).pack(side="left", padx=(8, 0))

        self.count_label = ttk.Label(top_frame, text="0 files selected")
        self.count_label.pack(side="right")

        # File list
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 2))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, selectmode="extended")
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)

        hint = "Tip: drag & drop PDF/image files or folders anywhere in this window" if DND_AVAILABLE else \
            "(Drag & drop unavailable - install 'tkinterdnd2' to enable it)"
        ttk.Label(self.root, text=hint, foreground="#666").pack(anchor="w", padx=12, pady=(0, 4))

        # Options
        opts_frame = ttk.LabelFrame(self.root, text="Options")
        opts_frame.pack(fill="x", padx=10, pady=6)

        out_row = ttk.Frame(opts_frame)
        out_row.pack(fill="x", padx=8, pady=6)
        ttk.Label(out_row, text="Export location:").pack(side="left")
        self.output_entry = ttk.Entry(out_row, textvariable=self.output_dir)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out_row, text="Browse...", command=self.choose_output_dir).pack(side="left")

        settings_row = ttk.Frame(opts_frame)
        settings_row.pack(fill="x", padx=8, pady=(0, 4))

        ttk.Label(settings_row, text="Output format:").pack(side="left")
        format_combo = ttk.Combobox(
            settings_row, values=["JPG", "PNG", "WEBP"], textvariable=self.output_format,
            state="readonly", width=6,
        )
        format_combo.pack(side="left", padx=(4, 16))

        ttk.Label(settings_row, text="PDF render DPI:").pack(side="left")
        dpi_spin = ttk.Spinbox(settings_row, from_=72, to=600, increment=10, textvariable=self.dpi, width=6)
        dpi_spin.pack(side="left", padx=(4, 16))

        ttk.Label(settings_row, text="Quality (JPG/WEBP):").pack(side="left")
        quality_spin = ttk.Spinbox(settings_row, from_=10, to=100, increment=5, textvariable=self.quality, width=6)
        quality_spin.pack(side="left", padx=(4, 0))

        checks_row = ttk.Frame(opts_frame)
        checks_row.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Checkbutton(
            checks_row,
            text="Subfolder per PDF",
            variable=self.subfolder_per_pdf,
        ).pack(side="left")

        ttk.Checkbutton(
            checks_row,
            text="Combine each PDF's pages into one image",
            variable=self.combine_pages,
        ).pack(side="left", padx=(16, 0))

        ttk.Checkbutton(
            checks_row,
            text="Skip files already converted",
            variable=self.skip_existing,
        ).pack(side="left", padx=(16, 0))

        # Progress
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill="x", padx=10, pady=(0, 6))

        self.progress = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress.pack(fill="x")

        self.status_label = ttk.Label(progress_frame, text="Ready.")
        self.status_label.pack(anchor="w", pady=(4, 0))

        # Log
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 6))
        self.log_text = tk.Text(log_frame, height=8, state="disabled", wrap="none")
        self.log_text.pack(fill="both", expand=True)

        # Action buttons
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.convert_btn = ttk.Button(action_frame, text="Convert", command=self.start_conversion)
        self.convert_btn.pack(side="left")

        self.cancel_btn = ttk.Button(action_frame, text="Cancel", command=self.cancel_conversion, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        self.open_output_btn = ttk.Button(action_frame, text="Open Output Folder", command=self.open_output_folder)
        self.open_output_btn.pack(side="right")

        if DND_AVAILABLE:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)

    # ---------- File selection ----------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF or image files",
            filetypes=[
                ("PDF and image files", "*.pdf *.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif"),
                ("PDF files", "*.pdf"),
                ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif"),
                ("All files", "*.*"),
            ],
        )
        self._add_paths(Path(p) for p in paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select a folder containing PDF/image files")
        if not folder:
            return
        found = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS)
        self._add_paths(found)

    def _on_drop(self, event):
        try:
            raw_paths = self.root.tk.splitlist(event.data)
        except Exception:
            raw_paths = [event.data]

        collected = []
        for raw in raw_paths:
            p = Path(raw)
            if p.is_dir():
                collected.extend(sorted(x for x in p.rglob("*") if x.suffix.lower() in SUPPORTED_EXTENSIONS))
            elif p.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected.append(p)
        if collected:
            self._add_paths(collected)
        else:
            self.log("Dropped item(s) contained no supported PDF/image files.")

    def _add_paths(self, paths):
        added = 0
        existing = set(self.files)
        for p in paths:
            if p not in existing:
                self.files.append(p)
                self.listbox.insert("end", str(p))
                existing.add(p)
                added += 1
        self.count_label.config(text=f"{len(self.files)} files selected")
        if added:
            self.log(f"Added {added} file(s).")

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self.count_label.config(text="0 files selected")

    def choose_output_dir(self):
        folder = filedialog.askdirectory(title="Select export location")
        if folder:
            self.output_dir.set(folder)

    def open_output_folder(self):
        out = self.output_dir.get().strip()
        if not out or not os.path.isdir(out):
            messagebox.showinfo("No folder", "Please choose a valid export location first.")
            return
        os.startfile(out)

    # ---------- Logging ----------
    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ---------- Config persistence ----------
    def _current_config(self):
        return {
            "output_dir": self.output_dir.get(),
            "dpi": self.dpi.get(),
            "quality": self.quality.get(),
            "subfolder_per_pdf": self.subfolder_per_pdf.get(),
            "combine_pages": self.combine_pages.get(),
            "skip_existing": self.skip_existing.get(),
            "output_format": self.output_format.get(),
        }

    def _on_close(self):
        save_config(self._current_config())
        self.root.destroy()

    # ---------- Conversion ----------
    def start_conversion(self):
        if not self.files:
            messagebox.showwarning("No files", "Please add at least one PDF or image file.")
            return
        out_dir = self.output_dir.get().strip()
        if not out_dir:
            messagebox.showwarning("No export location", "Please choose an export location.")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Invalid folder", f"Could not create/access output folder:\n{e}")
            return

        save_config(self._current_config())

        self.cancel_requested = False
        self.convert_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress.config(value=0, maximum=len(self.files))
        self.status_label.config(text=f"Converting 0 / {len(self.files)} files...")

        self.worker_thread = threading.Thread(
            target=self._convert_worker,
            args=(
                list(self.files), out_dir, self.dpi.get(), self.quality.get(),
                self.subfolder_per_pdf.get(), self.combine_pages.get(),
                self.skip_existing.get(), self.output_format.get(),
            ),
            daemon=True,
        )
        self.worker_thread.start()

    def cancel_conversion(self):
        self.cancel_requested = True
        self.cancel_btn.config(state="disabled")
        self.status_label.config(text="Cancelling...")

    def _request_password(self, pdf_name):
        result = {"password": None}
        event = threading.Event()
        self.progress_queue.put(("password_request", pdf_name, result, event))
        event.wait()
        return result["password"]

    def _convert_worker(self, files, out_dir, dpi, quality, use_subfolder, combine, skip_existing, out_format):
        total = len(files)
        done_files = 0
        total_images = 0
        skipped = 0
        errors = []
        ext = FORMAT_TO_EXT[out_format]
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        for idx, path in enumerate(files, start=1):
            if self.cancel_requested:
                self.progress_queue.put(("log", f"Cancelled after {idx - 1} file(s)."))
                break

            suffix = path.suffix.lower()
            try:
                if suffix in PDF_EXTENSIONS:
                    made, skip_count, errs = self._convert_pdf(
                        path, out_dir, matrix, quality, use_subfolder, combine, skip_existing, out_format, ext,
                    )
                elif suffix in IMAGE_EXTENSIONS:
                    made, skip_count, errs = self._convert_image(
                        path, out_dir, quality, skip_existing, out_format, ext,
                    )
                else:
                    made, skip_count, errs = 0, 0, [f"{path.name}: unsupported file type"]
            except Exception as e:
                made, skip_count, errs = 0, 0, [f"{path.name}: {e}"]

            total_images += made
            skipped += skip_count
            errors.extend(errs)
            done_files += 1
            self.progress_queue.put(("file_done", idx, total, path.name))

        self.progress_queue.put(("finished", done_files, total_images, skipped, errors))

    def _convert_pdf(self, pdf_path, out_dir, matrix, quality, use_subfolder, combine, skip_existing, out_format, ext):
        stem = pdf_path.stem
        target_dir = Path(out_dir) / stem if use_subfolder else Path(out_dir)

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            return 0, 0, [f"{pdf_path.name}: could not open ({e})"]

        if doc.needs_pass:
            password = self._request_password(pdf_path.name)
            if not password or not doc.authenticate(password):
                doc.close()
                return 0, 0, [f"{pdf_path.name}: incorrect or missing password, skipped"]

        page_count = doc.page_count

        if combine:
            out_name = f"{stem}.{ext}"
            out_path = target_dir / out_name
            if skip_existing and out_path.exists():
                doc.close()
                return 0, 1, []
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                doc.close()
                return 0, 0, [f"{pdf_path.name}: could not create output folder ({e})"]

            page_images = []
            errors = []
            for page_index in range(page_count):
                if self.cancel_requested:
                    break
                try:
                    page = doc.load_page(page_index)
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    mode = "RGB" if pix.n < 4 else "RGBA"
                    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                    page_images.append(img)
                except Exception as e:
                    errors.append(f"{pdf_path.name} page {page_index + 1}: {e}")
            doc.close()

            if not page_images:
                return 0, 0, errors or [f"{pdf_path.name}: no pages rendered"]

            max_width = max(im.width for im in page_images)
            total_height = sum(im.height for im in page_images)
            combined = Image.new("RGB", (max_width, total_height), (255, 255, 255))
            y = 0
            for im in page_images:
                combined.paste(im, ((max_width - im.width) // 2, y))
                y += im.height

            try:
                save_pil_image(combined, str(out_path), out_format, quality)
                return 1, 0, errors
            except Exception as e:
                return 0, 0, errors + [f"{pdf_path.name}: could not save combined image ({e})"]

        # Per-page output
        if skip_existing:
            marker_name = f"{stem}.{ext}" if page_count == 1 else f"{stem}_page001.{ext}"
            if (target_dir / marker_name).exists():
                doc.close()
                return 0, 1, []

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            doc.close()
            return 0, 0, [f"{pdf_path.name}: could not create output folder ({e})"]

        made = 0
        errors = []
        for page_index in range(page_count):
            if self.cancel_requested:
                break
            try:
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                mode = "RGB" if pix.n < 4 else "RGBA"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                out_name = f"{stem}.{ext}" if page_count == 1 else f"{stem}_page{page_index + 1:03d}.{ext}"
                out_path = target_dir / out_name
                save_pil_image(img, str(out_path), out_format, quality)
                made += 1
            except Exception as e:
                errors.append(f"{pdf_path.name} page {page_index + 1}: {e}")

        doc.close()
        return made, 0, errors

    def _convert_image(self, img_path, out_dir, quality, skip_existing, out_format, ext):
        stem = img_path.stem
        out_path = Path(out_dir) / f"{stem}.{ext}"

        if img_path.resolve() == out_path.resolve():
            return 0, 0, [f"{img_path.name}: source and destination are the same file, skipped"]

        if skip_existing and out_path.exists():
            return 0, 1, []

        try:
            with Image.open(img_path) as img:
                img.load()
                save_pil_image(img, str(out_path), out_format, quality)
            return 1, 0, []
        except Exception as e:
            return 0, 0, [f"{img_path.name}: {e}"]

    # ---------- UI polling ----------
    def _poll_queue(self):
        try:
            while True:
                item = self.progress_queue.get_nowait()
                kind = item[0]
                if kind == "file_done":
                    _, idx, total, name = item
                    self.progress.config(value=idx)
                    self.status_label.config(text=f"Converting {idx} / {total} files... ({name})")
                elif kind == "log":
                    self.log(item[1])
                elif kind == "password_request":
                    _, name, result, event = item
                    password = simpledialog.askstring(
                        "Password required",
                        f"'{name}' is password-protected.\nEnter password:",
                        show="*",
                        parent=self.root,
                    )
                    result["password"] = password
                    event.set()
                elif kind == "finished":
                    _, done_files, total_images, skipped, errors = item
                    self._on_finished(done_files, total_images, skipped, errors)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_finished(self, done_files, total_images, skipped, errors):
        self.convert_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        status = "Cancelled." if self.cancel_requested else "Done."
        summary = f"Converted {done_files} file(s) into {total_images} image(s)."
        if skipped:
            summary += f" Skipped {skipped} already-converted file(s)."
        self.status_label.config(text=f"{status} {summary}")
        self.log(f"{status} {summary}")
        for err in errors:
            self.log(f"ERROR: {err}")
        if not self.cancel_requested:
            messagebox.showinfo(
                "Conversion complete",
                summary + "\n" + (f"{len(errors)} error(s) occurred - see log." if errors else "No errors."),
            )


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    app = ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
