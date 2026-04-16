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

from flask import Flask, session

from services.app_paths import AppPaths
from services.config_service import ConfigService
from services.template_service import TemplateService
from services.job_manager import JobManager
from services.image_render_service import ImageRenderService
from services.print_worker import PrintWorker

from routes.public_routes import register_public_routes
from routes.admin_routes import register_admin_routes

BASE_DIR = os.path.expanduser("~/photoprint")

def create_app():
    # Paths
    paths = AppPaths(BASE_DIR)
    paths.ensure_dirs()

    # Services
    config_service = ConfigService(paths)
    template_service = TemplateService(paths)
    job_manager = JobManager()
    image_service = ImageRenderService(paths, template_service)

    # Flask app
    app = Flask(__name__)
    app.secret_key = config_service.load_config().get("session_secret", "local-secret")
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

    # Helper auth
    def admin_required():
        return bool(session.get("admin_ok"))

    # Worker
    print_worker = PrintWorker(job_manager, image_service, config_service)
    print_worker.start()

    # Route registration
    register_public_routes(
        app=app,
        paths=paths,
        config_service=config_service,
        template_service=template_service,
        job_manager=job_manager,
        image_service=image_service,
    )

    register_admin_routes(
        app=app,
        paths=paths,
        config_service=config_service,
        template_service=template_service,
        job_manager=job_manager,
        image_service=image_service,
        admin_required=admin_required,
    )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)   

    
