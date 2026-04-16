import json
import os
from datetime import datetime


class ConfigService:
    def __init__(self, paths):
        self.paths = paths

    # -----------------------------
    # DEFAULT CONFIG
    # -----------------------------
    def default_config(self) -> dict:
        return {
            "printer_name": "DNP_RX1",

            # branding
            "brand_name": "ÉPOQUE",
            "brand_tagline": "Luxury Photobooth Experience",

            # evento
            "event_name": "Evento",
            "event_date": datetime.now().strftime("%d.%m.%Y"),

            # limiti
            "max_copies": 5,
            "max_file_age_hours": 24,

            # sicurezza
            "admin_password": "admin",
            "session_secret": "local-secret",

            # UI / comportamento
            "enable_gallery": True,
            "auto_cleanup": True,
            "default_print_format": "10x15"
        }

    # -----------------------------
    # LOAD
    # -----------------------------
    def load_config(self) -> dict:
        default = self.default_config()

        if not os.path.exists(self.paths.CONFIG_PATH):
            return default

        try:
            with open(self.paths.CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return default

            default.update(data)

        except Exception:
            return default

        return default

    # -----------------------------
    # SAVE
    # -----------------------------
    def save_config(self, new_data: dict) -> dict:
        config = self.load_config()

        # merge dati nuovi
        config.update(new_data)

        # sicurezza base
        config["max_copies"] = int(config.get("max_copies", 5))
        config["max_file_age_hours"] = int(config.get("max_file_age_hours", 24))

        with open(self.paths.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return config

    # -----------------------------
    # UPDATE FIELD SINGOLO
    # -----------------------------
    def set(self, key: str, value):
        config = self.load_config()
        config[key] = value
        return self.save_config(config)

    # -----------------------------
    # GET FIELD
    # -----------------------------
    def get(self, key: str, default=None):
        config = self.load_config()
        return config.get(key, default)

    # -----------------------------
    # RESET CONFIG
    # -----------------------------
    def reset(self) -> dict:
        config = self.default_config()

        with open(self.paths.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return config

    # -----------------------------
    # VALIDAZIONE (utile admin)
    # -----------------------------
    def validate(self, data: dict) -> tuple[bool, str]:
        try:
            if "max_copies" in data:
                val = int(data["max_copies"])
                if val < 1 or val > 20:
                    return False, "max_copies deve essere tra 1 e 20"

            if "max_file_age_hours" in data:
                val = int(data["max_file_age_hours"])
                if val < 1 or val > 168:
                    return False, "max_file_age_hours deve essere tra 1 e 168"

        except Exception:
            return False, "Valori non validi"

        return True, "ok"