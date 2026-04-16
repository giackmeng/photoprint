import os
import csv
import uuid
import time
import json
import queue
import base64
import threading
import subprocess
from io import BytesIO
from datetime import datetime

from flask import (
    Flask, request, render_template, jsonify, url_for,
    abort, redirect, session, send_file
)
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, ImageDraw, ImageFont

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
SIZE_10X15 = (1200, 1800)
SIZE_STRIP = (600, 1800)
BASE_DIR = os.path.expanduser("~/photoprint")
paths = AppPaths(BASE_DIR)
paths.ensure_dirs()
config_service = ConfigService(paths)

app = Flask(__name__)
app.secret_key = config_service.load_config().get("session_secret", "local-secret")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

class AppPaths:
    def __init__(self,base_dir):
        self.BASE_DIR = base_dir
        self.UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
        self.PROCESSED_FOLDER = os.path.join(BASE_DIR, "processed")
        self.PREVIEW_FOLDER = os.path.join(BASE_DIR, "previews")
        self.EXPORT_FOLDER = os.path.join(BASE_DIR, "exports")
        self.ASSETS_FOLDER = os.path.join(BASE_DIR, "assets")
        self.CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
        self.TEMPLATES_CONFIG_PATH = os.path.join(BASE_DIR, "templates_config.json")
    def ensure_dirs(self):
        for folder in [
            self.UPLOAD_FOLDER,
            self.PROCESSED_FOLDER,
            self.PREVIEW_FOLDER,
            self.EXPORT_FOLDER,
            self.ASSETS_FOLDER,
        ]:
            os.makedirs(folder, exist_ok=True)



class ConfigService:
    def __init__(self,paths):
        self.paths=paths

    def load_config(self):
        default = {
            "printer_name": "DNP_RX1",
            "brand_name": "ÉPOQUE",
            "brand_tagline": "Luxury Photobooth Experience",
            "event_name": "Evento",
            "event_date": datetime.now().strftime("%d.%m.%Y"),
            "max_copies": 5,
            "max_file_age_hours": 24,
            "admin_password": "admin",
            "session_secret": "local-secret"
        }

        if not os.path.exists(self.paths.CONFIG_PATH):
            return default

        try:
            with open(self.paths.CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            default.update(data)
        except Exception:
            pass

        return default
    
    def save_config(self,new_data):
        config = self.load_config()
        config.update(new_data)
        with open(self.paths.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)





print_queue = queue.Queue()
jobs = {}
jobs_lock = threading.Lock()




def refresh_app_secret():
    app.secret_key = load_config().get("session_secret", "local-secret")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def make_unique_filename(extension):
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"


def fit_cover(img, size):
    return ImageOps.fit(
        img,
        size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )


def cleanup_old_files(folder, max_age_seconds):
    now = time.time()
    if not os.path.isdir(folder):
        return

    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            if now - os.path.getmtime(path) > max_age_seconds:
                os.remove(path)
        except Exception:
            pass


def cleanup_old_jobs(max_age_seconds):
    now = time.time()
    with jobs_lock:
        to_delete = []
        for job_id, job in jobs.items():
            ref = job.get("completed_at") or job.get("created_at", now)
            if now - ref > max_age_seconds:
                to_delete.append(job_id)
        for job_id in to_delete:
            jobs.pop(job_id, None)


def get_font(size, bold=False):
    candidates = []
    if bold:
        candidates.append("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_centered_text(draw, y, text, font, fill, canvas_width):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (canvas_width - text_w) // 2
    draw.text((x, y), text, font=font, fill=fill)


def add_logo(canvas):
    logo_path = os.path.join(ASSETS_FOLDER, "logo.png")
    if not os.path.exists(logo_path):
        return

    try:
        logo = Image.open(logo_path).convert("RGBA")
        max_width = 180
        scale = min(max_width / max(logo.width, 1), 1.0)
        new_size = (int(logo.width * scale), int(logo.height * scale))
        logo = logo.resize(new_size, Image.Resampling.LANCZOS)
        x = (canvas.width - logo.width) // 2
        y = 28
        canvas.paste(logo, (x, y), logo)
    except Exception:
        pass


def prepare_10x15(img):

    img = ImageOps.exif_transpose(img).convert("RGB")

    width, height = img.size

    # 👉 se orizzontale → ruota
    if width > height:
        img = img.rotate(90, expand=True)

    # ora è sempre verticale
    return ImageOps.fit(
        img,
        (1200, 1800),
        Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )
  #  return fit_cover(img, SIZE_10X15).convert("RGB")


def prepare_strip(img, config):
    canvas = Image.new("RGB", SIZE_STRIP, "white")
    draw = ImageDraw.Draw(canvas)

    font_brand = get_font(30, bold=True)
    font_sub = get_font(18)
    font_event = get_font(22, bold=True)
    font_footer = get_font(18)

    add_logo(canvas)

    brand_name = config.get("brand_name", "ÉPOQUE")
    brand_tagline = config.get("brand_tagline", "Luxury Photobooth Experience")
    event_name = config.get("event_name", "Evento")
    event_date = config.get("event_date", datetime.now().strftime("%d.%m.%Y"))

    draw_centered_text(draw, 110, brand_name, font_brand, (20, 20, 20), canvas.width)
    draw_centered_text(draw, 150, brand_tagline, font_sub, (95, 95, 95), canvas.width)
    draw_centered_text(draw, 185, event_name, font_event, (55, 55, 55), canvas.width)

    margin_x = 30
    top_photos = 250
    gap = 24
    bottom_reserved = 120
    frame_w = SIZE_STRIP[0] - (margin_x * 2)
    usable_h = SIZE_STRIP[1] - top_photos - bottom_reserved
    frame_h = (usable_h - gap * 2) // 3

    framed = fit_cover(img, (frame_w, frame_h)).convert("RGB")

    y = top_photos
    for _ in range(3):
        canvas.paste(framed, (margin_x, y))
        y += frame_h + gap

    draw_centered_text(draw, SIZE_STRIP[1] - 78, event_date, font_footer, (105, 105, 105), canvas.width)
    draw_centered_text(draw, SIZE_STRIP[1] - 48, f"Printed with {brand_name}", font_footer, (105, 105, 105), canvas.width)

    return canvas
    
def prepare_strip_from_paths(image_paths, config):
    images = []

    for path in image_paths[:3]:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            images.append(img.copy())

    if not images:
        raise ValueError("Nessuna immagine valida per la strip")

    if len(images) == 1:
        slots = [images[0], images[0], images[0]]
    elif len(images) == 2:
        slots = [images[0], images[1], images[0]]
    else:
        slots = [images[0], images[1], images[2]]

    canvas = Image.new("RGB", SIZE_STRIP, "white")
    draw = ImageDraw.Draw(canvas)

    font_brand = get_font(30, bold=True)
    font_sub = get_font(18)
    font_event = get_font(22, bold=True)
    font_footer = get_font(18)

    add_logo(canvas)

    brand_name = config.get("brand_name", "ÉPOQUE")
    brand_tagline = config.get("brand_tagline", "Luxury Photobooth Experience")
    event_name = config.get("event_name", "Evento")
    event_date = config.get("event_date", datetime.now().strftime("%d.%m.%Y"))

    draw_centered_text(draw, 110, brand_name, font_brand, (20, 20, 20), canvas.width)
    draw_centered_text(draw, 150, brand_tagline, font_sub, (95, 95, 95), canvas.width)
    draw_centered_text(draw, 185, event_name, font_event, (55, 55, 55), canvas.width)

    margin_x = 30
    top_photos = 250
    gap = 24
    bottom_reserved = 120
    frame_w = SIZE_STRIP[0] - (margin_x * 2)
    usable_h = SIZE_STRIP[1] - top_photos - bottom_reserved
    frame_h = (usable_h - gap * 2) // 3

    y = top_photos
    for img in slots:
        framed = fit_cover(img, (frame_w, frame_h)).convert("RGB")
        canvas.paste(framed, (margin_x, y))
        y += frame_h + gap

    draw_centered_text(draw, SIZE_STRIP[1] - 78, event_date, font_footer, (105, 105, 105), canvas.width)
    draw_centered_text(draw, SIZE_STRIP[1] - 48, f"Printed with {brand_name}", font_footer, (105, 105, 105), canvas.width)

    return canvas
    
def generate_preview_base64_from_paths(image_paths, print_format, config):
    tpl = get_active_template(print_format)

    # Caso speciale: strip con più foto
    if print_format == "strip" and image_paths:
        if tpl and tpl.get("mode") == "image_template_multi":
            images = []

            for path in image_paths[:3]:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    images.append(img.copy())

            if not images:
                raise ValueError("Nessuna immagine valida per l'anteprima strip")

            while len(images) < 3:
                images.append(images[0].copy())

            template_path = os.path.join(ASSETS_FOLDER, tpl["template_file"])
            canvas = Image.open(template_path).convert("RGBA")
            photo_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 0))

            fit_mode = tpl.get("photo_fit", "cover")
            boxes = tpl.get("photo_boxes", [])

            for idx, box in enumerate(boxes[:3]):
                img = images[idx]
                x, y, w, h = box

                if fit_mode == "contain":
                    fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
                    paste_x = x + (w - fitted.width) // 2
                    paste_y = y + (h - fitted.height) // 2
                else:
                    fitted = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    paste_x = x
                    paste_y = y

                photo_layer.paste(fitted.convert("RGBA"), (paste_x, paste_y))

            final_img = Image.alpha_composite(photo_layer, canvas).convert("RGB")
        else:
            final_img = prepare_strip_from_paths(image_paths, config)

        preview = final_img.copy()
        preview.thumbnail((300, 500))

        buffer = BytesIO()
        preview.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"

    # Fallback: usa la prima immagine
    if not image_paths:
        raise ValueError("Nessuna immagine disponibile per l'anteprima")

    return generate_preview_base64(image_paths[0], print_format, config)    

def create_job(original_path=None, original_paths=None, processed_path=None, print_format="10x15", copies=1):
    job_id = uuid.uuid4().hex[:12]
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "original_path": original_path,
            "original_paths": original_paths or ([] if original_path is None else [original_path]),
            "processed_path": processed_path,
            "print_format": print_format,
            "copies": copies,
            "message": "In coda",
            "printer_job_id": None,
            "cancelled": False
        }
    return job_id


def get_queue_position(job_id):
    with jobs_lock:
        queued_ids = [jid for jid, data in jobs.items() if data["status"] == "queued"]
        queued_ids.sort(key=lambda x: jobs[x]["created_at"])
        if job_id in queued_ids:
            return queued_ids.index(job_id) + 1
    return 0


def build_stats():
    with jobs_lock:
        total = len(jobs)
        queued = sum(1 for j in jobs.values() if j["status"] == "queued")
        processing = sum(1 for j in jobs.values() if j["status"] == "processing")
        done = sum(1 for j in jobs.values() if j["status"] == "done")
        errors = sum(1 for j in jobs.values() if j["status"] == "error")
        cancelled = sum(1 for j in jobs.values() if j.get("cancelled"))
        total_copies = sum(int(j.get("copies", 0)) for j in jobs.values() if j["status"] == "done")
    return {
        "total": total,
        "queued": queued,
        "processing": processing,
        "done": done,
        "errors": errors,
        "cancelled": cancelled,
        "total_copies": total_copies
    }


def worker():
    while True:
        job_id = print_queue.get()
        config = config_service.load_config()

        try:
            with jobs_lock:
             job = jobs.get(job_id)
            if not job:
                print_queue.task_done()
                continue

            if job.get("cancelled"):
                job["status"] = "error"
                job["message"] = "Job annullato"
                job["completed_at"] = time.time()
                print_queue.task_done()
                continue

            job["status"] = "processing"
            job["started_at"] = time.time()
            job["message"] = "Preparazione e stampa in corso"

            original_path = job.get("original_path")
            original_paths = job.get("original_paths", [])
            processed_path = job["processed_path"]
            print_format = job["print_format"]
            copies = job["copies"]
              
            prepare_image(
                input_path=original_path,
                output_path=processed_path,
                print_format=print_format,
                config=config,
                input_paths=original_paths
            )

            with jobs_lock:
                if jobs[job_id].get("cancelled"):
                    jobs[job_id]["status"] = "error"
                    jobs[job_id]["message"] = "Job annullato"
                    jobs[job_id]["completed_at"] = time.time()
                    print_queue.task_done()
                    continue

            result = subprocess.run(
                ["lp", "-d", config["printer_name"], "-n", str(copies), processed_path],
                capture_output=True,
                text=True,
                check=True
            )

            printer_job_id = None
            stdout = result.stdout.strip()
            if stdout:
                for token in stdout.split():
                    if "-" in token and "(" not in token:
                        printer_job_id = token
                        break

            with jobs_lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["completed_at"] = time.time()
                jobs[job_id]["message"] = stdout or "Stampa inviata con successo"
                jobs[job_id]["printer_job_id"] = printer_job_id

        except subprocess.CalledProcessError as e:
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "error"
                    jobs[job_id]["completed_at"] = time.time()
                    jobs[job_id]["message"] = e.stderr.strip() if e.stderr else "Errore stampa"

        except Exception as e:
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "error"
                    jobs[job_id]["completed_at"] = time.time()
                    jobs[job_id]["message"] = f"Errore: {str(e)}"

        finally:
            print_queue.task_done()


worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()

def admin_required():
    return bool(session.get("admin_ok"))

class TemplateService:
    def __init__(self,paths):
        self.paths = paths

    def load_templates_config():
        default = {
            "active_template_10x15": None,
            "active_template_strip": None,
            "templates": []
        }

        if not os.path.exists(TEMPLATES_CONFIG_PATH):
            return default

        try:
            with open(self.paths.TEMPLATES_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            default.update(data)
           
        except Exception:
            pass

        return default

//SEI ARRIVATO QUI
    def get_active_template(self,print_format):
        data = self.load_templates_config()
        active_id = data.get("active_template_10x15") if print_format == "10x15" else data.get("active_template_strip")

        for tpl in data.get("templates", []):
            if tpl.get("id") == active_id and tpl.get("print_format") == print_format:
                return tpl

        return None


def place_image_in_box(base_canvas, img, box, fit_mode="cover"):
    x, y, w, h = box

    if fit_mode == "contain":
        fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
        paste_x = x + (w - fitted.width) // 2
        paste_y = y + (h - fitted.height) // 2
    else:
        fitted = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        paste_x = x
        paste_y = y

    base_canvas.paste(fitted, (paste_x, paste_y))


def render_generated_10x15(img, config, tpl):
    canvas = Image.new("RGB", (1200, 1800), tpl.get("background_color", "#f8f5f0"))
    draw = ImageDraw.Draw(canvas)

    photo_box = tpl.get("photo_box", [100, 80, 1000, 1350])
    place_image_in_box(canvas, img, photo_box, fit_mode="cover")

    font_brand = get_font(34, bold=True)
    font_event = get_font(26, bold=True)
    font_small = get_font(20)

    if tpl.get("show_brand", True):
        draw_centered_text(draw, 1490, config.get("brand_name", "ÉPOQUE"), font_brand, (25, 25, 25), 1200)

    if tpl.get("show_event_name", True):
        draw_centered_text(draw, 1545, config.get("event_name", "Evento"), font_event, (70, 70, 70), 1200)

    if tpl.get("show_event_date", True):
        draw_centered_text(draw, 1595, config.get("event_date", "01.01.2027"), font_small, (110, 110, 110), 1200)

    return canvas


def render_image_template(img, tpl):
    template_path = os.path.join(ASSETS_FOLDER, tpl["template_file"])
    canvas = Image.open(template_path).convert("RGBA")

    photo_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
    photo_box = tpl["photo_box"]
    fit_mode = tpl.get("photo_fit", "cover")

    x, y, w, h = photo_box

    if fit_mode == "contain":
        fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
        paste_x = x + (w - fitted.width) // 2
        paste_y = y + (h - fitted.height) // 2
    else:
        fitted = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        paste_x = x
        paste_y = y

    photo_layer.paste(fitted.convert("RGBA"), (paste_x, paste_y))
    final = Image.alpha_composite(photo_layer, canvas)

    return final.convert("RGB")


def render_image_template_multi(img, tpl):
    template_path = os.path.join(ASSETS_FOLDER, tpl["template_file"])
    canvas = Image.open(template_path).convert("RGBA")
    photo_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 0))

    fit_mode = tpl.get("photo_fit", "cover")
    boxes = tpl.get("photo_boxes", [])

    for box in boxes:
        x, y, w, h = box

        if fit_mode == "contain":
            fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
            paste_x = x + (w - fitted.width) // 2
            paste_y = y + (h - fitted.height) // 2
        else:
            fitted = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            paste_x = x
            paste_y = y

        photo_layer.paste(fitted.convert("RGBA"), (paste_x, paste_y))

    final = Image.alpha_composite(photo_layer, canvas)
    return final.convert("RGB")


def prepare_image(input_path, output_path, print_format, config, input_paths=None):
    tpl = get_active_template(print_format)

    # Caso speciale: strip con più foto
    if print_format == "strip" and input_paths and len(input_paths) > 1:
        if tpl and tpl.get("mode") == "image_template_multi":
            images = []
            for path in input_paths[:3]:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    images.append(img.copy())

            while len(images) < 3:
                images.append(images[0].copy())

            template_path = os.path.join(ASSETS_FOLDER, tpl["template_file"])
            canvas = Image.open(template_path).convert("RGBA")
            photo_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 0))

            fit_mode = tpl.get("photo_fit", "cover")
            boxes = tpl.get("photo_boxes", [])

            for idx, box in enumerate(boxes[:3]):
                img = images[idx]
                x, y, w, h = box

                if fit_mode == "contain":
                    fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
                    paste_x = x + (w - fitted.width) // 2
                    paste_y = y + (h - fitted.height) // 2
                else:
                    fitted = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    paste_x = x
                    paste_y = y

                photo_layer.paste(fitted.convert("RGBA"), (paste_x, paste_y))

            final_img = Image.alpha_composite(photo_layer, canvas).convert("RGB")
            final_img.save(output_path, format="JPEG", quality=95)
            return

        else:
            final_img = prepare_strip_from_paths(input_paths, config)
            final_img.save(output_path, format="JPEG", quality=95)
            return

    # Caso standard: una sola immagine
    with Image.open(input_path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        width, height = img.size

        if tpl and tpl.get("rotate_landscape") and width > height:
            img = img.rotate(90, expand=True)

        if tpl:
            mode = tpl.get("mode")

            if mode == "generated":
                final_img = render_generated_10x15(img, config, tpl)
            elif mode == "image_template":
                final_img = render_image_template(img, tpl)
            elif mode == "image_template_multi":
                final_img = prepare_strip(img, config) if print_format == "strip" else prepare_10x15(img)
            elif mode == "auto_orientation":
                final_img = render_auto_orientation_template(img, tpl)
            else:
                final_img = prepare_strip(img, config) if print_format == "strip" else prepare_10x15(img)
        else:
            final_img = prepare_strip(img, config) if print_format == "strip" else prepare_10x15(img)

        final_img.save(output_path, format="JPEG", quality=95)

def generate_preview_base64(input_path, print_format, config):
    tpl = get_active_template(print_format)

    with Image.open(input_path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        width, height = img.size

        if tpl and tpl.get("rotate_landscape") and width > height:
            img = img.rotate(90, expand=True)

        if tpl:
            mode = tpl.get("mode")

            if mode == "generated":
                final_img = render_generated_10x15(img, config, tpl)
            elif mode == "image_template":
                final_img = render_image_template(img, tpl)
            elif mode == "image_template_multi":
                final_img = render_image_template_multi(img, tpl)
            elif mode == "auto_orientation":
             final_img = render_auto_orientation_template(img, tpl)    
            else:
                final_img = prepare_strip(img, config) if print_format == "strip" else prepare_10x15(img)
        else:
            final_img = prepare_strip(img, config) if print_format == "strip" else prepare_10x15(img)

        preview = final_img.copy()
        preview.thumbnail((300, 500))

        buffer = BytesIO()
        preview.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"


@app.route("/", methods=["GET"])
def home():
    config = config_service.load_config()
    max_age_seconds = int(config.get("max_file_age_hours", 24)) * 3600
    cleanup_old_files(UPLOAD_FOLDER, max_age_seconds)
    cleanup_old_files(PROCESSED_FOLDER, max_age_seconds)
    cleanup_old_files(PREVIEW_FOLDER, max_age_seconds)
    cleanup_old_jobs(max_age_seconds)
    return render_template("index.html", config=config)


@app.route("/success/<job_id>", methods=["GET"])
def success(job_id):
    config = config_service.load_config()
    with jobs_lock:
        job = jobs.get(job_id)
    return render_template("success.html", config=config, job=job)


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"success": False, "message": "Job non trovato"}), 404

    return jsonify({
        "success": True,
        "job_id": job["id"],
        "status": job["status"],
        "message": job["message"],
        "queue_position": get_queue_position(job_id),
        "copies": job["copies"],
        "print_format": job["print_format"]
    })


@app.route("/queue-info", methods=["GET"])
def queue_info():
    stats = build_stats()
    return jsonify({
        "queued": stats["queued"],
        "processing": stats["processing"]
    })


@app.route("/preview", methods=["POST"])
def preview():
    config = config_service.load_config()

    if "photo" not in request.files:
        return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

    file = request.files["photo"]
    print_format = request.form.get("print_format", "10x15")

    if file.filename == "":
        return jsonify({"success": False, "message": "Nessuna foto selezionata"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Formato non supportato"}), 400

    if print_format not in ["10x15", "strip"]:
        return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    temp_path = os.path.join(PREVIEW_FOLDER, make_unique_filename(ext))

    try:
        file.save(temp_path)
        preview_data = generate_preview_base64(temp_path, print_format, config)
        return jsonify({"success": True, "preview": preview_data})
    except Exception as e:
        return jsonify({"success": False, "message": f"Errore preview: {str(e)}"}), 500


@app.route("/print", methods=["POST"])
def print_photo():
    config = config_service.load_config()

    if "photo" not in request.files:
        return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

    file = request.files["photo"]
    copies = request.form.get("copies", "1")
    print_format = request.form.get("print_format", "10x15")

    if file.filename == "":
        return jsonify({"success": False, "message": "Nessuna foto selezionata"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Formato non supportato"}), 400

    try:
        copies = int(copies)
        max_copies = int(config.get("max_copies", 5))
        if copies < 1 or copies > max_copies:
            return jsonify({"success": False, "message": "Numero copie non valido"}), 400
    except ValueError:
        return jsonify({"success": False, "message": "Numero copie non valido"}), 400

    if print_format not in ["10x15", "strip"]:
        return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    original_path = os.path.join(UPLOAD_FOLDER, make_unique_filename(ext))
    processed_path = os.path.join(PROCESSED_FOLDER, make_unique_filename("jpg"))

    try:
        file.save(original_path)
        job_id = create_job(original_path, processed_path, print_format, copies)
        print_queue.put(job_id)

        return jsonify({
            "success": True,
            "job_id": job_id,
            "queue_position": get_queue_position(job_id),
            "redirect": url_for("success", job_id=job_id)
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Errore salvataggio file: {str(e)}"}), 500

@app.route("/preview-multiple", methods=["POST"])
def preview_multiple():
    config = config_service.load_config()

    if "photos" not in request.files:
        return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

    files = request.files.getlist("photos")
    print_format = request.form.get("print_format", "10x15")

    valid_files = [f for f in files if f and f.filename.strip()]

    if not valid_files:
        return jsonify({"success": False, "message": "Nessuna foto selezionata"}), 400

    if len(valid_files) > 3:
        return jsonify({"success": False, "message": "Puoi usare massimo 3 foto per l'anteprima"}), 400

    if print_format not in ["10x15", "strip"]:
        return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

    temp_paths = []

    try:
        for file in valid_files:
            if not allowed_file(file.filename):
                continue

            ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
            temp_path = os.path.join(PREVIEW_FOLDER, make_unique_filename(ext))
            file.save(temp_path)
            temp_paths.append(temp_path)

        if not temp_paths:
            return jsonify({"success": False, "message": "Nessun file valido per l'anteprima"}), 400

        preview_data = generate_preview_base64_from_paths(temp_paths, print_format, config)
        return jsonify({"success": True, "preview": preview_data})

    except Exception as e:
        return jsonify({"success": False, "message": f"Errore preview: {str(e)}"}), 500

def render_auto_orientation_template(img, tpl):
    width, height = img.size

    if width > height:
        # ORIZZONTALE
        template_file = tpl.get("template_landscape")
        box = tpl.get("photo_box_landscape")
    else:
        # VERTICALE
        template_file = tpl.get("template_portrait")
        box = tpl.get("photo_box_portrait")

    template_path = os.path.join(ASSETS_FOLDER, template_file)

    canvas = Image.open(template_path).convert("RGBA")
    photo_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 0))

    x, y, w, h = box
    fit_mode = tpl.get("photo_fit", "cover")

    if fit_mode == "contain":
        fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
        paste_x = x + (w - fitted.width) // 2
        paste_y = y + (h - fitted.height) // 2
    else:
        fitted = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        paste_x = x
        paste_y = y

    photo_layer.paste(fitted.convert("RGBA"), (paste_x, paste_y))
    final = Image.alpha_composite(photo_layer, canvas)

    return final.convert("RGB")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    config = config_service.load_config()

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == config.get("admin_password"):
            session["admin_ok"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Password non corretta")

    return render_template("admin_login.html", error=None)


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin", methods=["GET"])
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))

    config = config_service.load_config()
    templates_cfg = load_templates_config()

    with jobs_lock:
        ordered_jobs = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)[:100]

    stats = build_stats()

    templates_10x15 = [t for t in templates_cfg.get("templates", []) if t.get("print_format") == "10x15"]
    templates_strip = [t for t in templates_cfg.get("templates", []) if t.get("print_format") == "strip"]

    return render_template(
        "admin.html",
        config=config,
        jobs=ordered_jobs,
        stats=stats,
        templates_cfg=templates_cfg,
        templates_10x15=templates_10x15,
        templates_strip=templates_strip
    )

@app.route("/admin/jobs", methods=["GET"])
def admin_jobs():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    with jobs_lock:
        ordered_jobs = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)[:100]
        data = []
        for job in ordered_jobs:
            data.append({
                "id": job["id"],
                "status": job["status"],
                "message": job["message"],
                "copies": job["copies"],
                "print_format": job["print_format"],
                "created_at": datetime.fromtimestamp(job["created_at"]).strftime("%d/%m %H:%M:%S"),
                "printer_job_id": job.get("printer_job_id") or "",
                "cancelled": job.get("cancelled", False)
            })
    return jsonify({"success": True, "jobs": data, "stats": build_stats()})


@app.route("/admin/reprint/<job_id>", methods=["POST"])
def admin_reprint(job_id):
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    with jobs_lock:
        src_job = jobs.get(job_id)
        if not src_job or not os.path.exists(src_job["original_path"]):
            return jsonify({"success": False, "message": "Job non disponibile"}), 404

        new_job_id = create_job(
        original_path=src_job.get("original_path"),
        original_paths=src_job.get("original_paths", [src_job.get("original_path")]),
        processed_path=os.path.join(PROCESSED_FOLDER, make_unique_filename("jpg")),
        print_format=src_job["print_format"],
        copies=src_job["copies"]
        )

        print_queue.put(new_job_id)
    return jsonify({"success": True, "message": "Ristampa aggiunta in coda"})


@app.route("/admin/reprint-last", methods=["POST"])
def admin_reprint_last():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    with jobs_lock:
        done_jobs = [j for j in jobs.values() if j["status"] == "done" and os.path.exists(j["original_path"])]
        done_jobs.sort(key=lambda j: j["created_at"], reverse=True)

        if not done_jobs:
            return jsonify({"success": False, "message": "Nessun job completato disponibile"}), 404

        src_job = done_jobs[0]
        new_job_id = create_job(
            original_path=src_job["original_path"],
            processed_path=os.path.join(PROCESSED_FOLDER, make_unique_filename("jpg")),
            print_format=src_job["print_format"],
            copies=src_job["copies"]
        )

    print_queue.put(new_job_id)
    return jsonify({"success": True, "message": "Ristampa ultimo job aggiunta in coda"})


@app.route("/admin/cancel/<job_id>", methods=["POST"])
def admin_cancel(job_id):
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"success": False, "message": "Job non trovato"}), 404
        if job["status"] != "queued":
            return jsonify({"success": False, "message": "Puoi annullare solo job in coda"}), 400

        job["cancelled"] = True
        job["status"] = "error"
        job["message"] = "Job annullato manualmente"
        job["completed_at"] = time.time()

    return jsonify({"success": True, "message": "Job annullato"})


@app.route("/admin/config", methods=["POST"])
def admin_config():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    data = {
        "printer_name": request.form.get("printer_name", "").strip(),
        "brand_name": request.form.get("brand_name", "").strip(),
        "brand_tagline": request.form.get("brand_tagline", "").strip(),
        "event_name": request.form.get("event_name", "").strip(),
        "event_date": request.form.get("event_date", "").strip(),
        "max_copies": int(request.form.get("max_copies", "5")),
        "max_file_age_hours": int(request.form.get("max_file_age_hours", "24"))
    }

    save_config(data)
    refresh_app_secret()
    return jsonify({"success": True, "message": "Configurazione aggiornata"})


@app.route("/admin/upload-logo", methods=["POST"])
def admin_upload_logo():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    if "logo" not in request.files:
        return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

    logo = request.files["logo"]
    if logo.filename == "":
        return jsonify({"success": False, "message": "Nessun file selezionato"}), 400

    ext = secure_filename(logo.filename).rsplit(".", 1)[-1].lower()
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        return jsonify({"success": False, "message": "Formato logo non supportato"}), 400

    path = os.path.join(ASSETS_FOLDER, "logo.png")
    try:
        with Image.open(logo.stream) as img:
            img = ImageOps.exif_transpose(img).convert("RGBA")
            img.save(path, format="PNG")
        return jsonify({"success": True, "message": "Logo aggiornato"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Errore upload logo: {str(e)}"}), 500


@app.route("/admin/export", methods=["GET"])
def admin_export():
    if not admin_required():
        return redirect(url_for("admin_login"))

    export_path = os.path.join(EXPORT_FOLDER, f"jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    with jobs_lock:
        ordered_jobs = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)

    with open(export_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "job_id", "status", "message", "format", "copies",
            "created_at", "started_at", "completed_at", "printer_job_id", "cancelled"
        ])
        for job in ordered_jobs:
            writer.writerow([
                job["id"],
                job["status"],
                job["message"],
                job["print_format"],
                job["copies"],
                datetime.fromtimestamp(job["created_at"]).strftime("%Y-%m-%d %H:%M:%S") if job["created_at"] else "",
                datetime.fromtimestamp(job["started_at"]).strftime("%Y-%m-%d %H:%M:%S") if job["started_at"] else "",
                datetime.fromtimestamp(job["completed_at"]).strftime("%Y-%m-%d %H:%M:%S") if job["completed_at"] else "",
                job.get("printer_job_id") or "",
                job.get("cancelled", False)
            ])

    return send_file(export_path, as_attachment=True)


@app.route("/admin/cleanup", methods=["POST"])
def admin_cleanup():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    config = config_service.load_config()
    max_age_seconds = int(config.get("max_file_age_hours", 24)) * 3600
    cleanup_old_files(UPLOAD_FOLDER, max_age_seconds)
    cleanup_old_files(PROCESSED_FOLDER, max_age_seconds)
    cleanup_old_files(PREVIEW_FOLDER, max_age_seconds)
    cleanup_old_jobs(max_age_seconds)
    return jsonify({"success": True, "message": "Pulizia completata"})

@app.route("/admin/templates", methods=["POST"])
def admin_templates():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    data = load_templates_config()
    data["active_template_10x15"] = request.form.get("active_template_10x15", "").strip()
    data["active_template_strip"] = request.form.get("active_template_strip", "").strip()

    with open(TEMPLATES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "message": "Template attivi aggiornati"})

@app.route("/print-multiple", methods=["POST"])
def print_multiple():
    config = config_service.load_config()

    if "photos" not in request.files:
        return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

    files = request.files.getlist("photos")
    copies = request.form.get("copies", "1")
    print_format = request.form.get("print_format", "10x15")

    valid_files = [f for f in files if f and f.filename.strip()]

    if not valid_files:
        return jsonify({"success": False, "message": "Nessuna foto selezionata"}), 400

    if len(valid_files) > 3:
        return jsonify({"success": False, "message": "Puoi inviare massimo 3 foto per volta"}), 400

    try:
        copies = int(copies)
        max_copies = int(config.get("max_copies", 5))
        if copies < 1 or copies > max_copies:
            return jsonify({"success": False, "message": "Numero copie non valido"}), 400
    except ValueError:
        return jsonify({"success": False, "message": "Numero copie non valido"}), 400

    if print_format not in ["10x15", "strip"]:
        return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

    try:
        # Caso STRIP: tutte le foto in un solo job
        if print_format == "strip":
            original_paths = []

            for file in valid_files[:3]:
                if not allowed_file(file.filename):
                    continue

                ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
                original_path = os.path.join(UPLOAD_FOLDER, make_unique_filename(ext))
                file.save(original_path)
                original_paths.append(original_path)

            if not original_paths:
                return jsonify({"success": False, "message": "Nessun file valido da usare per la strip"}), 400

            processed_path = os.path.join(PROCESSED_FOLDER, make_unique_filename("jpg"))

            job_id = create_job(
                original_path=original_paths[0],
                original_paths=original_paths,
                processed_path=processed_path,
                print_format="strip",
                copies=copies
            )

            print_queue.put(job_id)

            return jsonify({
                "success": True,
                "message": f"Strip creata con {len(original_paths)} foto e inviata alla coda di stampa",
                "job_ids": [job_id]
            })

        # Caso 10x15: un job per foto
        created_jobs = []

        for file in valid_files:
            if not allowed_file(file.filename):
                continue

            ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
            original_path = os.path.join(UPLOAD_FOLDER, make_unique_filename(ext))
            processed_path = os.path.join(PROCESSED_FOLDER, make_unique_filename("jpg"))

            file.save(original_path)

            job_id = create_job(
                original_path=original_path,
                original_paths=[original_path],
                processed_path=processed_path,
                print_format=print_format,
                copies=copies
            )

            print_queue.put(job_id)
            created_jobs.append(job_id)

        if not created_jobs:
            return jsonify({"success": False, "message": "Nessun file valido da stampare"}), 400

        return jsonify({
            "success": True,
            "message": f"{len(created_jobs)} foto inviate correttamente alla coda di stampa",
            "job_ids": created_jobs
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Errore invio multiplo: {str(e)}"
        }), 500

@app.route("/admin/templates-list", methods=["GET"])
def admin_templates_list():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    data = load_templates_config()
    return jsonify({
        "success": True,
        "active_template_10x15": data.get("active_template_10x15"),
        "active_template_strip": data.get("active_template_strip"),
        "templates": data.get("templates", [])
    })

@app.route("/admin/template-boxes", methods=["POST"])
def admin_template_boxes():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    template_id = request.form.get("template_id", "").strip()
    if not template_id:
        return jsonify({"success": False, "message": "Template ID mancante"}), 400

    data = load_templates_config()
    templates = data.get("templates", [])

    target = None
    for tpl in templates:
        if tpl.get("id") == template_id:
            target = tpl
            break

    if not target:
        return jsonify({"success": False, "message": "Template non trovato"}), 404

    try:
        if target.get("mode") == "image_template_multi" or target.get("print_format") == "strip":
            box1 = [
                int(request.form.get("box1_x", "0")),
                int(request.form.get("box1_y", "0")),
                int(request.form.get("box1_w", "0")),
                int(request.form.get("box1_h", "0")),
            ]
            box2 = [
                int(request.form.get("box2_x", "0")),
                int(request.form.get("box2_y", "0")),
                int(request.form.get("box2_w", "0")),
                int(request.form.get("box2_h", "0")),
            ]
            box3 = [
                int(request.form.get("box3_x", "0")),
                int(request.form.get("box3_y", "0")),
                int(request.form.get("box3_w", "0")),
                int(request.form.get("box3_h", "0")),
            ]

            for box in (box1, box2, box3):
                if box[2] <= 0 or box[3] <= 0:
                    return jsonify({"success": False, "message": "Larghezza e altezza devono essere maggiori di zero"}), 400

            target["photo_boxes"] = [box1, box2, box3]
        else:
            photo_box = [
                int(request.form.get("photo_x", "0")),
                int(request.form.get("photo_y", "0")),
                int(request.form.get("photo_w", "0")),
                int(request.form.get("photo_h", "0")),
            ]

            if photo_box[2] <= 0 or photo_box[3] <= 0:
                return jsonify({"success": False, "message": "Larghezza e altezza devono essere maggiori di zero"}), 400

            target["photo_box"] = photo_box

        fit = request.form.get("photo_fit", "").strip()
        if fit in {"cover", "contain"}:
            target["photo_fit"] = fit

        with open(TEMPLATES_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True, "message": "Box foto aggiornati con successo"})

    except ValueError:
        return jsonify({"success": False, "message": "Valori box non validi"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Errore aggiornamento box: {str(e)}"}), 500   

@app.route("/admin/template-detail/<template_id>", methods=["GET"])
def admin_template_detail(template_id):
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    data = load_templates_config()

    for tpl in data.get("templates", []):
        if tpl.get("id") == template_id:
            return jsonify({"success": True, "template": tpl})

    return jsonify({"success": False, "message": "Template non trovato"}), 404

@app.route("/admin/upload-template", methods=["POST"])
def admin_upload_template():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    if "template_file" not in request.files:
        return jsonify({"success": False, "message": "Nessun file template ricevuto"}), 400

    template_file = request.files["template_file"]
    if template_file.filename == "":
        return jsonify({"success": False, "message": "Nessun file selezionato"}), 400

    ext = secure_filename(template_file.filename).rsplit(".", 1)[-1].lower()
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        return jsonify({"success": False, "message": "Formato template non supportato"}), 400

    template_id = request.form.get("template_id", "").strip()
    label = request.form.get("label", "").strip()
    print_format = request.form.get("print_format", "").strip()
    mode = request.form.get("mode", "").strip()

    if not template_id:
        return jsonify({"success": False, "message": "template_id obbligatorio"}), 400

    if not label:
        return jsonify({"success": False, "message": "label obbligatoria"}), 400

    if print_format not in {"10x15", "strip"}:
        return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

    if mode not in {"image_template", "image_template_multi"}:
        return jsonify({"success": False, "message": "Mode non valido"}), 400

    filename = f"{template_id}.{ext}"
    save_path = os.path.join(ASSETS_FOLDER, filename)

    try:
        with Image.open(template_file.stream) as img:
            img = ImageOps.exif_transpose(img)

            expected_size = (1200, 1800) if print_format == "10x15" else (600, 1800)

            if img.size != expected_size:
                return jsonify({
                    "success": False,
                    "message": f"Dimensione non valida. Atteso {expected_size[0]}x{expected_size[1]} px, trovato {img.size[0]}x{img.size[1]} px"
                }), 400

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")

            if ext == "png":
                img.save(save_path, format="PNG")
            elif ext in {"jpg", "jpeg"}:
                img.convert("RGB").save(save_path, format="JPEG", quality=95)
            elif ext == "webp":
                img.save(save_path, format="WEBP", quality=95)

    except Exception as e:
        return jsonify({"success": False, "message": f"Errore lettura template: {str(e)}"}), 500

    data = load_templates_config()

    # rimuove eventuale template con stesso id
    templates = [t for t in data.get("templates", []) if t.get("id") != template_id]

    # box di default, modificabili poi a mano nel json
    if print_format == "10x15":
        tpl = {
            "id": template_id,
            "label": label,
            "print_format": "10x15",
            "mode": "image_template",
            "template_file": filename,
            "photo_box": [110, 120, 980, 1280],
            "photo_fit": "cover",
            "rotate_landscape": True
        }
    else:
        tpl = {
            "id": template_id,
            "label": label,
            "print_format": "strip",
            "mode": "image_template_multi",
            "template_file": filename,
            "photo_boxes": [
                [30, 250, 540, 450],
                [30, 724, 540, 450],
                [30, 1198, 540, 450]
            ],
            "photo_fit": "cover"
        }

    templates.append(tpl)
    data["templates"] = templates

    with open(TEMPLATES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "success": True,
        "message": f"Template '{label}' caricato correttamente",
        "template_id": template_id,
        "template_file": filename
    })

@app.route("/admin/template-preview-file/<template_id>", methods=["GET"])
def admin_template_preview_file(template_id):
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    data = load_templates_config()

    for tpl in data.get("templates", []):
        if tpl.get("id") == template_id:
            template_file = tpl.get("template_file")
            if not template_file:
                return jsonify({"success": False, "message": "Template file mancante"}), 404

            path = os.path.join(ASSETS_FOLDER, template_file)
            if not os.path.exists(path):
                return jsonify({"success": False, "message": "File template non trovato"}), 404

            return send_file(path)

    return jsonify({"success": False, "message": "Template non trovato"}), 404

@app.route("/admin/template-render-preview", methods=["POST"])
def admin_template_render_preview():
    if not admin_required():
        return jsonify({"success": False, "message": "Non autorizzato"}), 403

    if "photo" not in request.files:
        return jsonify({"success": False, "message": "Nessuna foto"}), 400

    file = request.files["photo"]

    try:
        img = Image.open(file.stream)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        return jsonify({"success": False, "message": "Immagine non valida"}), 400

    template_id = request.form.get("template_id")

    data = load_templates_config()
    tpl = next((t for t in data.get("templates", []) if t.get("id") == template_id), None)

    if not tpl:
        return jsonify({"success": False, "message": "Template non trovato"}), 404

    try:
        # override box live (quelli modificati da UI)
        if tpl.get("mode") == "image_template_multi" or tpl.get("print_format") == "strip":
            tpl["photo_boxes"] = [
                [int(request.form.get("box1_x", 0)), int(request.form.get("box1_y", 0)),
                 int(request.form.get("box1_w", 0)), int(request.form.get("box1_h", 0))],
                [int(request.form.get("box2_x", 0)), int(request.form.get("box2_y", 0)),
                 int(request.form.get("box2_w", 0)), int(request.form.get("box2_h", 0))],
                [int(request.form.get("box3_x", 0)), int(request.form.get("box3_y", 0)),
                 int(request.form.get("box3_w", 0)), int(request.form.get("box3_h", 0))]
            ]
        else:
            tpl["photo_box"] = [
                int(request.form.get("photo_x", 0)),
                int(request.form.get("photo_y", 0)),
                int(request.form.get("photo_w", 0)),
                int(request.form.get("photo_h", 0))
            ]

        tpl["photo_fit"] = request.form.get("photo_fit", "cover")

        # render reale
        if tpl.get("mode") == "image_template":
            final = render_image_template(img, tpl)
        elif tpl.get("mode") == "image_template_multi":
            final = render_image_template_multi(img, tpl)
        else:
            final = prepare_10x15(img)

        buffer = BytesIO()
        final.thumbnail((400, 700))
        final.save(buffer, format="JPEG", quality=85)

        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return jsonify({
            "success": True,
            "preview": f"data:image/jpeg;base64,{encoded}"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({"success": False, "message": "File troppo grande. Carica un'immagine sotto i 20 MB."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
