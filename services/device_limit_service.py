import json
import os
import re
import subprocess
import threading
from datetime import datetime


class DeviceLimitService:
    def __init__(self, paths):
        self.paths = paths
        self.db_path = os.path.join(paths.BASE_DIR, "device_print_limits.json")
        self.lock = threading.Lock()

    def _default_db(self):
        return {
            "max_prints_per_mac": 3,
            "devices": {}
        }

    def load_db(self):
        if not os.path.exists(self.db_path):
            return self._default_db()

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._default_db()
            if "devices" not in data or not isinstance(data["devices"], dict):
                data["devices"] = {}
            if "max_prints_per_mac" not in data:
                data["max_prints_per_mac"] = 3
            return data
        except Exception:
            return self._default_db()

    def save_db(self, data):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def set_global_limit(self, limit: int):
        with self.lock:
            data = self.load_db()
            data["max_prints_per_mac"] = max(1, int(limit))
            self.save_db(data)
            return data["max_prints_per_mac"]

    def get_global_limit(self):
        data = self.load_db()
        return int(data.get("max_prints_per_mac", 3))

    def get_client_ip(self, flask_request):
        forwarded = flask_request.headers.get("X-Forwarded-For", "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
        return (flask_request.remote_addr or "").strip()

    def normalize_mac(self, mac: str):
        if not mac:
            return None
        mac = mac.strip().lower().replace("-", ":")
        if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", mac):
            return mac
        return None

    def get_mac_from_ip(self, ip: str):
        if not ip:
            return None

        try:
            result = subprocess.run(
                ["ip", "neigh", "show", ip],
                capture_output=True,
                text=True,
                check=False
            )
            out = (result.stdout or "").strip()
            m = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", out)
            if m:
                return self.normalize_mac(m.group(1))
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["arp", "-n", ip],
                capture_output=True,
                text=True,
                check=False
            )
            out = (result.stdout or "").strip()
            m = re.search(r"(([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2})", out)
            if m:
                return self.normalize_mac(m.group(1))
        except Exception:
            pass

        return None

    def get_client_mac(self, flask_request):
        ip = self.get_client_ip(flask_request)
        mac = self.get_mac_from_ip(ip)
        return ip, mac

    def get_device_record(self, mac: str):
        mac = self.normalize_mac(mac)
        if not mac:
            return None

        data = self.load_db()
        return data["devices"].get(mac, {
            "prints_used": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })

    def can_print(self, mac: str, requested_prints: int = 1):
        mac = self.normalize_mac(mac)
        if not mac:
            return False, "MAC address non disponibile"

        data = self.load_db()
        limit = int(data.get("max_prints_per_mac", 3))
        record = data["devices"].get(mac, {
            "prints_used": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })

        used = int(record.get("prints_used", 0))
        requested_prints = max(1, int(requested_prints))

        if used + requested_prints > limit:
            remaining = max(0, limit - used)
            return False, f"Limite raggiunto per questo dispositivo. Rimanenti: {remaining}"

        return True, "OK"

    def register_print(self, mac: str, count: int = 1):
        mac = self.normalize_mac(mac)
        if not mac:
            return False

        with self.lock:
            data = self.load_db()
            devices = data["devices"]

            if mac not in devices:
                devices[mac] = {
                    "prints_used": 0,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }

            devices[mac]["prints_used"] = int(devices[mac].get("prints_used", 0)) + max(1, int(count))
            devices[mac]["updated_at"] = datetime.now().isoformat()

            self.save_db(data)
            return True

    def get_remaining(self, mac: str):
        mac = self.normalize_mac(mac)
        if not mac:
            return 0

        data = self.load_db()
        limit = int(data.get("max_prints_per_mac", 3))
        record = data["devices"].get(mac, {"prints_used": 0})
        used = int(record.get("prints_used", 0))
        return max(0, limit - used)

    def reset_device(self, mac: str):
        mac = self.normalize_mac(mac)
        if not mac:
            return False

        with self.lock:
            data = self.load_db()
            if mac in data["devices"]:
                data["devices"][mac]["prints_used"] = 0
                data["devices"][mac]["updated_at"] = datetime.now().isoformat()
                self.save_db(data)
            return True

    def list_devices(self):
        data = self.load_db()
        limit = int(data.get("max_prints_per_mac", 3))
        rows = []

        for mac, rec in data.get("devices", {}).items():
            used = int(rec.get("prints_used", 0))
            rows.append({
                "mac": mac,
                "prints_used": used,
                "remaining": max(0, limit - used),
                "created_at": rec.get("created_at", ""),
                "updated_at": rec.get("updated_at", "")
            })

        rows.sort(key=lambda x: x["updated_at"], reverse=True)
        return rows