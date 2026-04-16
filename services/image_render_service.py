import os
import time
import uuid
import base64
from io import BytesIO
from datetime import datetime

from PIL import Image, ImageOps, ImageDraw, ImageFont


class ImageRenderService:
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    SIZE_10X15 = (1200, 1800)
    SIZE_STRIP = (600, 1800)

    def __init__(self, paths, template_service):
        self.paths = paths
        self.template_service = template_service

    # -----------------------------
    # Utility base
    # -----------------------------
    def allowed_file(self, filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in self.ALLOWED_EXTENSIONS

    def make_unique_filename(self, extension: str) -> str:
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"

    def cleanup_old_files(self, folder: str, max_age_seconds: int) -> None:
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

    def fit_cover(self, img: Image.Image, size: tuple[int, int]) -> Image.Image:
        return ImageOps.fit(
            img,
            size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5)
        )

    def get_font(self, size: int, bold: bool = False):
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

    def draw_centered_text(self, draw: ImageDraw.ImageDraw, y: int, text: str, font, fill, canvas_width: int) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = (canvas_width - text_w) // 2
        draw.text((x, y), text, font=font, fill=fill)

    def add_logo(self, canvas: Image.Image) -> None:
        logo_path = os.path.join(self.paths.ASSETS_FOLDER, "logo.png")
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

    # -----------------------------
    # Colori / placeholders / layers
    # -----------------------------
    def hex_to_rgb(self, value: str, default=(0, 0, 0)):
        try:
            value = value.strip().lstrip("#")
            if len(value) == 6:
                return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
        return default

    def replace_placeholders(self, text: str, config: dict) -> str:
        if not isinstance(text, str):
            return ""

        return (
            text.replace("{brand_name}", config.get("brand_name", ""))
            .replace("{brand_tagline}", config.get("brand_tagline", ""))
            .replace("{event_name}", config.get("event_name", ""))
            .replace("{event_date}", config.get("event_date", ""))
        )

    def draw_text_layer(self, draw: ImageDraw.ImageDraw, layer: dict, config: dict, canvas_width: int) -> None:
        text = self.replace_placeholders(layer.get("text", ""), config)
        font_size = int(layer.get("font_size", 24))
        font_bold = bool(layer.get("font_bold", False))
        color = self.hex_to_rgb(layer.get("color", "#000000"))
        x = int(layer.get("x", 0))
        y = int(layer.get("y", 0))
        align = layer.get("align", "left")

        font = self.get_font(font_size, bold=font_bold)

        if align == "center":
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text((x - text_w // 2, y), text, font=font, fill=color)
        elif align == "right":
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text((x - text_w, y), text, font=font, fill=color)
        else:
            draw.text((x, y), text, font=font, fill=color)

    def draw_rect_layer(self, draw: ImageDraw.ImageDraw, layer: dict) -> None:
        x = int(layer.get("x", 0))
        y = int(layer.get("y", 0))
        w = int(layer.get("w", 0))
        h = int(layer.get("h", 0))
        outline = self.hex_to_rgb(layer.get("outline", "#000000"))
        fill = layer.get("fill")
        fill_rgb = self.hex_to_rgb(fill) if fill else None
        width = int(layer.get("width", 1))

        draw.rectangle([x, y, x + w, y + h], outline=outline, fill=fill_rgb, width=width)

    def draw_image_layer(self, canvas: Image.Image, layer: dict) -> None:
        file_name = layer.get("file")
        if not file_name:
            return

        path = os.path.join(self.paths.ASSETS_FOLDER, file_name)
        if not os.path.exists(path):
            return

        try:
            overlay = Image.open(path).convert("RGBA")
            x = int(layer.get("x", 0))
            y = int(layer.get("y", 0))
            w = int(layer.get("w", overlay.width))
            h = int(layer.get("h", overlay.height))

            overlay = overlay.resize((w, h), Image.Resampling.LANCZOS)
            canvas.paste(overlay, (x, y), overlay)
        except Exception:
            pass

    def apply_layers(self, canvas: Image.Image, layers: list[dict], config: dict) -> Image.Image:
        if not layers:
            return canvas

        draw = ImageDraw.Draw(canvas)

        for layer in layers:
            layer_type = layer.get("type")

            if layer_type == "text":
                self.draw_text_layer(draw, layer, config, canvas.width)
            elif layer_type == "rect":
                self.draw_rect_layer(draw, layer)
            elif layer_type == "image":
                self.draw_image_layer(canvas, layer)

        return canvas

    # -----------------------------
    # Posizionamento immagine nel box
    # -----------------------------
    def place_image_in_box(self, base_canvas: Image.Image, img: Image.Image, box: list[int], fit_mode: str = "cover") -> None:
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

    # -----------------------------
    # Render 10x15 / strip base
    # -----------------------------
    def prepare_10x15(self, img: Image.Image) -> Image.Image:
        img = ImageOps.exif_transpose(img).convert("RGB")
        width, height = img.size

        if width > height:
            img = img.rotate(90, expand=True)

        return ImageOps.fit(
            img,
            self.SIZE_10X15,
            Image.Resampling.LANCZOS,
            centering=(0.5, 0.5)
        )

    def prepare_strip(self, img: Image.Image, config: dict) -> Image.Image:
        canvas = Image.new("RGB", self.SIZE_STRIP, "white")
        draw = ImageDraw.Draw(canvas)

        font_brand = self.get_font(30, bold=True)
        font_sub = self.get_font(18)
        font_event = self.get_font(22, bold=True)
        font_footer = self.get_font(18)

        self.add_logo(canvas)

        brand_name = config.get("brand_name", "ÉPOQUE")
        brand_tagline = config.get("brand_tagline", "Luxury Photobooth Experience")
        event_name = config.get("event_name", "Evento")
        event_date = config.get("event_date", datetime.now().strftime("%d.%m.%Y"))

        self.draw_centered_text(draw, 110, brand_name, font_brand, (20, 20, 20), canvas.width)
        self.draw_centered_text(draw, 150, brand_tagline, font_sub, (95, 95, 95), canvas.width)
        self.draw_centered_text(draw, 185, event_name, font_event, (55, 55, 55), canvas.width)

        margin_x = 30
        top_photos = 250
        gap = 24
        bottom_reserved = 120
        frame_w = self.SIZE_STRIP[0] - (margin_x * 2)
        usable_h = self.SIZE_STRIP[1] - top_photos - bottom_reserved
        frame_h = (usable_h - gap * 2) // 3

        framed = self.fit_cover(img, (frame_w, frame_h)).convert("RGB")

        y = top_photos
        for _ in range(3):
            canvas.paste(framed, (margin_x, y))
            y += frame_h + gap

        self.draw_centered_text(draw, self.SIZE_STRIP[1] - 78, event_date, font_footer, (105, 105, 105), canvas.width)
        self.draw_centered_text(draw, self.SIZE_STRIP[1] - 48, f"Printed with {brand_name}", font_footer, (105, 105, 105), canvas.width)

        return canvas

    def prepare_strip_from_paths(self, image_paths: list[str], config: dict) -> Image.Image:
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

        canvas = Image.new("RGB", self.SIZE_STRIP, "white")
        draw = ImageDraw.Draw(canvas)

        font_brand = self.get_font(30, bold=True)
        font_sub = self.get_font(18)
        font_event = self.get_font(22, bold=True)
        font_footer = self.get_font(18)

        self.add_logo(canvas)

        brand_name = config.get("brand_name", "ÉPOQUE")
        brand_tagline = config.get("brand_tagline", "Luxury Photobooth Experience")
        event_name = config.get("event_name", "Evento")
        event_date = config.get("event_date", datetime.now().strftime("%d.%m.%Y"))

        self.draw_centered_text(draw, 110, brand_name, font_brand, (20, 20, 20), canvas.width)
        self.draw_centered_text(draw, 150, brand_tagline, font_sub, (95, 95, 95), canvas.width)
        self.draw_centered_text(draw, 185, event_name, font_event, (55, 55, 55), canvas.width)

        margin_x = 30
        top_photos = 250
        gap = 24
        bottom_reserved = 120
        frame_w = self.SIZE_STRIP[0] - (margin_x * 2)
        usable_h = self.SIZE_STRIP[1] - top_photos - bottom_reserved
        frame_h = (usable_h - gap * 2) // 3

        y = top_photos
        for img in slots:
            framed = self.fit_cover(img, (frame_w, frame_h)).convert("RGB")
            canvas.paste(framed, (margin_x, y))
            y += frame_h + gap

        self.draw_centered_text(draw, self.SIZE_STRIP[1] - 78, event_date, font_footer, (105, 105, 105), canvas.width)
        self.draw_centered_text(draw, self.SIZE_STRIP[1] - 48, f"Printed with {brand_name}", font_footer, (105, 105, 105), canvas.width)

        return canvas

    # -----------------------------
    # Render template Canva/Photoshop
    # -----------------------------
    def render_generated_10x15(self, img: Image.Image, config: dict, tpl: dict) -> Image.Image:
        canvas = Image.new("RGB", self.SIZE_10X15, tpl.get("background_color", "#f8f5f0"))
        draw = ImageDraw.Draw(canvas)

        photo_box = tpl.get("photo_box", [100, 80, 1000, 1350])
        self.place_image_in_box(canvas, img, photo_box, fit_mode=tpl.get("photo_fit", "cover"))

        font_brand = self.get_font(34, bold=True)
        font_event = self.get_font(26, bold=True)
        font_small = self.get_font(20)

        if tpl.get("show_brand", True):
            self.draw_centered_text(draw, 1490, config.get("brand_name", "ÉPOQUE"), font_brand, (25, 25, 25), 1200)

        if tpl.get("show_event_name", True):
            self.draw_centered_text(draw, 1545, config.get("event_name", "Evento"), font_event, (70, 70, 70), 1200)

        if tpl.get("show_event_date", True):
            self.draw_centered_text(draw, 1595, config.get("event_date", "01.01.2027"), font_small, (110, 110, 110), 1200)

        return canvas

    def render_image_template(self, img: Image.Image, tpl: dict, config: dict | None = None) -> Image.Image:
        template_path = os.path.join(self.paths.ASSETS_FOLDER, tpl["template_file"])
        canvas = Image.open(template_path).convert("RGBA")

        photo_layer = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
        x, y, w, h = tpl["photo_box"]
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
        final = Image.alpha_composite(photo_layer, canvas).convert("RGB")

        if config:
            final = self.apply_layers(final, tpl.get("layers", []), config)

        return final

    def render_image_template_multi(self, img: Image.Image, tpl: dict, config: dict | None = None) -> Image.Image:
        template_path = os.path.join(self.paths.ASSETS_FOLDER, tpl["template_file"])
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

        final = Image.alpha_composite(photo_layer, canvas).convert("RGB")

        if config:
            final = self.apply_layers(final, tpl.get("layers", []), config)

        return final

    def render_auto_orientation_template(self, img: Image.Image, tpl: dict, config: dict | None = None) -> Image.Image:
        width, height = img.size

        if width > height:
            template_file = tpl.get("template_landscape")
            box = tpl.get("photo_box_landscape")
        else:
            template_file = tpl.get("template_portrait")
            box = tpl.get("photo_box_portrait")

        template_path = os.path.join(self.paths.ASSETS_FOLDER, template_file)
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
        final = Image.alpha_composite(photo_layer, canvas).convert("RGB")

        if config:
            final = self.apply_layers(final, tpl.get("layers", []), config)

        return final

    # -----------------------------
    # Render finale
    # -----------------------------
    def prepare_image(
        self,
        input_path: str | None,
        output_path: str,
        print_format: str,
        config: dict,
        input_paths: list[str] | None = None
    ) -> None:
        tpl = self.template_service.get_active_template(print_format)

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

                template_path = os.path.join(self.paths.ASSETS_FOLDER, tpl["template_file"])
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
                final_img = self.apply_layers(final_img, tpl.get("layers", []), config)
                final_img.save(output_path, format="JPEG", quality=95)
                return

            final_img = self.prepare_strip_from_paths(input_paths, config)
            final_img.save(output_path, format="JPEG", quality=95)
            return

        if not input_path:
            raise ValueError("input_path mancante")

        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            width, height = img.size

            if tpl and tpl.get("rotate_landscape") and width > height:
                img = img.rotate(90, expand=True)

            if tpl:
                mode = tpl.get("mode")

                if mode == "generated":
                    final_img = self.render_generated_10x15(img, config, tpl)
                elif mode == "image_template":
                    final_img = self.render_image_template(img, tpl, config)
                elif mode == "image_template_multi":
                    final_img = self.prepare_strip(img, config) if print_format == "strip" else self.prepare_10x15(img)
                elif mode == "auto_orientation":
                    final_img = self.render_auto_orientation_template(img, tpl, config)
                else:
                    final_img = self.prepare_strip(img, config) if print_format == "strip" else self.prepare_10x15(img)
            else:
                final_img = self.prepare_strip(img, config) if print_format == "strip" else self.prepare_10x15(img)

            final_img.save(output_path, format="JPEG", quality=95)

    # -----------------------------
    # Preview
    # -----------------------------
    def generate_preview_base64(self, input_path: str, print_format: str, config: dict) -> str:
        tpl = self.template_service.get_active_template(print_format)

        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            width, height = img.size

            if tpl and tpl.get("rotate_landscape") and width > height:
                img = img.rotate(90, expand=True)

            if tpl:
                mode = tpl.get("mode")

                if mode == "generated":
                    final_img = self.render_generated_10x15(img, config, tpl)
                elif mode == "image_template":
                    final_img = self.render_image_template(img, tpl, config)
                elif mode == "image_template_multi":
                    final_img = self.render_image_template_multi(img, tpl, config)
                elif mode == "auto_orientation":
                    final_img = self.render_auto_orientation_template(img, tpl, config)
                else:
                    final_img = self.prepare_strip(img, config) if print_format == "strip" else self.prepare_10x15(img)
            else:
                final_img = self.prepare_strip(img, config) if print_format == "strip" else self.prepare_10x15(img)

            preview = final_img.copy()
            preview.thumbnail((300, 500))

            buffer = BytesIO()
            preview.save(buffer, format="JPEG", quality=85)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"

    def generate_preview_base64_from_paths(self, image_paths: list[str], print_format: str, config: dict) -> str:
        tpl = self.template_service.get_active_template(print_format)

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

                template_path = os.path.join(self.paths.ASSETS_FOLDER, tpl["template_file"])
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
                final_img = self.apply_layers(final_img, tpl.get("layers", []), config)
            else:
                final_img = self.prepare_strip_from_paths(image_paths, config)

            preview = final_img.copy()
            preview.thumbnail((300, 500))

            buffer = BytesIO()
            preview.save(buffer, format="JPEG", quality=85)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"

        # fallback: prima foto
        if not image_paths:
            raise ValueError("Nessuna immagine disponibile per l'anteprima")

        return self.generate_preview_base64(image_paths[0], print_format, config)