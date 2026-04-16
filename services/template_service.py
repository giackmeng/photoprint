import json
import os


class TemplateService:
    def __init__(self, paths):
        self.paths = paths

    # -----------------------------
    # DEFAULT CONFIG
    # -----------------------------
    def default_templates_config(self) -> dict:
        return {
            "active_template_10x15": None,
            "active_template_strip": None,
            "templates": []
        }

    # -----------------------------
    # LOAD / SAVE
    # -----------------------------
    def load_templates_config(self) -> dict:
        default = self.default_templates_config()

        if not os.path.exists(self.paths.TEMPLATES_CONFIG_PATH):
            return default

        try:
            with open(self.paths.TEMPLATES_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return default

            default.update(data)
            if "templates" not in default or not isinstance(default["templates"], list):
                default["templates"] = []

        except Exception:
            return default

        return default

    def save_templates_config(self, data: dict) -> dict:
        base = self.default_templates_config()
        base.update(data)

        if "templates" not in base or not isinstance(base["templates"], list):
            base["templates"] = []

        with open(self.paths.TEMPLATES_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=2)

        return base

    # -----------------------------
    # LIST / GET
    # -----------------------------
    def list_templates(self) -> list:
        return self.load_templates_config().get("templates", [])

    def get_template_by_id(self, template_id: str):
        if not template_id:
            return None

        for tpl in self.list_templates():
            if tpl.get("id") == template_id:
                return tpl
        return None

    def get_active_template(self, print_format: str):
        data = self.load_templates_config()

        active_id = data.get("active_template_10x15") if print_format == "10x15" else data.get("active_template_strip")
        if not active_id:
            return None

        return self.get_template_by_id(active_id)

    def get_templates_by_format(self, print_format: str) -> list:
        return [t for t in self.list_templates() if t.get("print_format") == print_format]

    # -----------------------------
    # ACTIVE TEMPLATE
    # -----------------------------
    def set_active_templates(self, active_template_10x15=None, active_template_strip=None) -> dict:
        data = self.load_templates_config()

        if active_template_10x15 is not None:
            data["active_template_10x15"] = active_template_10x15 or None

        if active_template_strip is not None:
            data["active_template_strip"] = active_template_strip or None

        return self.save_templates_config(data)

    # -----------------------------
    # ADD / REPLACE TEMPLATE
    # -----------------------------
    def upsert_template(self, template_data: dict) -> dict:
        if not template_data.get("id"):
            raise ValueError("Template senza id")

        data = self.load_templates_config()
        templates = data.get("templates", [])

        replaced = False
        new_templates = []

        for tpl in templates:
            if tpl.get("id") == template_data["id"]:
                new_templates.append(template_data)
                replaced = True
            else:
                new_templates.append(tpl)

        if not replaced:
            new_templates.append(template_data)

        data["templates"] = new_templates
        self.save_templates_config(data)
        return template_data

    # -----------------------------
    # DELETE TEMPLATE
    # -----------------------------
    def delete_template(self, template_id: str) -> bool:
        data = self.load_templates_config()
        templates = data.get("templates", [])

        before = len(templates)
        templates = [tpl for tpl in templates if tpl.get("id") != template_id]
        after = len(templates)

        if before == after:
            return False

        data["templates"] = templates

        if data.get("active_template_10x15") == template_id:
            data["active_template_10x15"] = None

        if data.get("active_template_strip") == template_id:
            data["active_template_strip"] = None

        self.save_templates_config(data)
        return True

    # -----------------------------
    # BOX UPDATE
    # -----------------------------
    def update_template_boxes(self, template_id: str, photo_box=None, photo_boxes=None, photo_fit=None) -> dict:
        data = self.load_templates_config()
        templates = data.get("templates", [])

        updated = None

        for tpl in templates:
            if tpl.get("id") == template_id:
                if photo_box is not None:
                    tpl["photo_box"] = photo_box

                if photo_boxes is not None:
                    tpl["photo_boxes"] = photo_boxes

                if photo_fit in {"cover", "contain"}:
                    tpl["photo_fit"] = photo_fit

                updated = tpl
                break

        if not updated:
            raise ValueError("Template non trovato")

        self.save_templates_config(data)
        return updated

    # -----------------------------
    # LAYERS
    # -----------------------------
    def update_template_layers(self, template_id: str, layers: list) -> dict:
        data = self.load_templates_config()
        templates = data.get("templates", [])

        updated = None

        for tpl in templates:
            if tpl.get("id") == template_id:
                tpl["layers"] = layers if isinstance(layers, list) else []
                updated = tpl
                break

        if not updated:
            raise ValueError("Template non trovato")

        self.save_templates_config(data)
        return updated

    def add_layer_to_template(self, template_id: str, layer: dict) -> dict:
        data = self.load_templates_config()
        templates = data.get("templates", [])

        updated = None

        for tpl in templates:
            if tpl.get("id") == template_id:
                if "layers" not in tpl or not isinstance(tpl["layers"], list):
                    tpl["layers"] = []
                tpl["layers"].append(layer)
                updated = tpl
                break

        if not updated:
            raise ValueError("Template non trovato")

        self.save_templates_config(data)
        return updated

    # -----------------------------
    # HELPERS TEMPLATE
    # -----------------------------
    def build_single_image_template(
        self,
        template_id: str,
        label: str,
        print_format: str,
        template_file: str,
        photo_box: list,
        photo_fit: str = "cover",
        rotate_landscape: bool = True,
        layers: list | None = None
    ) -> dict:
        return {
            "id": template_id,
            "label": label,
            "print_format": print_format,
            "mode": "image_template",
            "template_file": template_file,
            "photo_box": photo_box,
            "photo_fit": photo_fit,
            "rotate_landscape": rotate_landscape,
            "layers": layers or []
        }

    def build_multi_image_template(
        self,
        template_id: str,
        label: str,
        print_format: str,
        template_file: str,
        photo_boxes: list,
        photo_fit: str = "cover",
        layers: list | None = None
    ) -> dict:
        return {
            "id": template_id,
            "label": label,
            "print_format": print_format,
            "mode": "image_template_multi",
            "template_file": template_file,
            "photo_boxes": photo_boxes,
            "photo_fit": photo_fit,
            "layers": layers or []
        }

    def build_generated_template(
        self,
        template_id: str,
        label: str,
        print_format: str = "10x15",
        background_color: str = "#f8f5f0",
        photo_box: list | None = None,
        show_brand: bool = True,
        show_event_name: bool = True,
        show_event_date: bool = True,
        rotate_landscape: bool = True,
        photo_fit: str = "cover",
        layers: list | None = None
    ) -> dict:
        return {
            "id": template_id,
            "label": label,
            "print_format": print_format,
            "mode": "generated",
            "background_color": background_color,
            "photo_box": photo_box or [100, 80, 1000, 1350],
            "photo_fit": photo_fit,
            "show_brand": show_brand,
            "show_event_name": show_event_name,
            "show_event_date": show_event_date,
            "rotate_landscape": rotate_landscape,
            "layers": layers or []
        }

    def build_auto_orientation_template(
        self,
        template_id: str,
        label: str,
        template_portrait: str,
        template_landscape: str,
        photo_box_portrait: list,
        photo_box_landscape: list,
        photo_fit: str = "cover",
        layers: list | None = None
    ) -> dict:
        return {
            "id": template_id,
            "label": label,
            "print_format": "10x15",
            "mode": "auto_orientation",
            "template_portrait": template_portrait,
            "template_landscape": template_landscape,
            "photo_box_portrait": photo_box_portrait,
            "photo_box_landscape": photo_box_landscape,
            "photo_fit": photo_fit,
            "layers": layers or []
        }