import uuid
import hashlib


class DeviceIdentityService:
    COOKIE_NAME = "photoprint_device_token"

    def get_or_create_browser_token(self, flask_request, flask_response=None):
        token = flask_request.cookies.get(self.COOKIE_NAME)

        if token and len(token) >= 16:
            return token

        token = uuid.uuid4().hex

        if flask_response is not None:
            flask_response.set_cookie(
                self.COOKIE_NAME,
                token,
                max_age=60 * 60 * 24 * 5,  # 5 days
                httponly=False,
                samesite="Lax"
            )

        return token

    def build_identity_key(self, event_code, browser_token, mac=None, ip=None):
        raw = f"{event_code}|{mac or ''}|{ip or ''}|{browser_token or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()