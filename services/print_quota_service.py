import json
import os
import threading
from datetime import datetime


class PrintQuotaService:
    def __init__(self, paths):
        self.paths = paths
        self.db_path = os.path.join(paths.BASE_DIR, "print_quota_db.json")
        self.lock = threading.Lock()

    def _default_db(self):
        return {
            "default_limit_per_identity": 3,
            "event_code": "EVENTO2026",
            "records": {}
        }

    def load_db(self):
        if not os.path.exists(self.db_path):
            return self._default_db()

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return self._default_db()

            if "records" not in data or not isinstance(data["records"], dict):
                data["records"] = {}

            if "default_limit_per_identity" not in data:
                data["default_limit_per_identity"] = 3

            if "event_code" not in data:
                data["event_code"] = "EVENTO2026"

            return data
        except Exception:
            return self._default_db()

    def save_db(self, data):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_event_code(self):
        data = self.load_db()
        return data.get("event_code", "EVENTO2026")

    def set_event_code(self, event_code):
        with self.lock:
            data = self.load_db()
            data["event_code"] = (event_code or "EVENTO2026").strip()
            self.save_db(data)
            return data["event_code"]

    def get_default_limit(self):
        data = self.load_db()
        return int(data.get("default_limit_per_identity", 3))

    def set_default_limit(self, limit):
        with self.lock:
            data = self.load_db()
            data["default_limit_per_identity"] = max(1, int(limit))
            self.save_db(data)
            return data["default_limit_per_identity"]

    def can_print(self, identity_key, requested_count=1):
        data = self.load_db()
        limit = int(data.get("default_limit_per_identity", 3))
        rec = data["records"].get(identity_key, {"prints_used": 0})

        used = int(rec.get("prints_used", 0))
        requested_count = max(1, int(requested_count))

        if used + requested_count > limit:
            remaining = max(0, limit - used)
            return False, remaining

        return True, max(0, limit - used)

    def register_print(self, identity_key, count=1, meta=None):
        with self.lock:
            data = self.load_db()
            records = data["records"]

            if identity_key not in records:
                records[identity_key] = {
                    "prints_used": 0,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "meta": {}
                }

            records[identity_key]["prints_used"] = int(records[identity_key].get("prints_used", 0)) + max(1, int(count))
            records[identity_key]["updated_at"] = datetime.now().isoformat()

            if meta:
                records[identity_key]["meta"] = meta

            self.save_db(data)

    def get_remaining(self, identity_key):
        data = self.load_db()
        limit = int(data.get("default_limit_per_identity", 3))
        rec = data["records"].get(identity_key, {"prints_used": 0})
        used = int(rec.get("prints_used", 0))
        return max(0, limit - used)

    def reset_identity(self, identity_key):
        with self.lock:
            data = self.load_db()
            if identity_key in data["records"]:
                data["records"][identity_key]["prints_used"] = 0
                data["records"][identity_key]["updated_at"] = datetime.now().isoformat()
                self.save_db(data)

    def list_records(self):
        data = self.load_db()
        limit = int(data.get("default_limit_per_identity", 3))
        rows = []

        for key, rec in data.get("records", {}).items():
            used = int(rec.get("prints_used", 0))
            rows.append({
                "identity_key": key,
                "prints_used": used,
                "remaining": max(0, limit - used),
                "updated_at": rec.get("updated_at", ""),
                "meta": rec.get("meta", {})
            })

        rows.sort(key=lambda x: x["updated_at"], reverse=True)
        return rows