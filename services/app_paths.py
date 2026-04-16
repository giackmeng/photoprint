import os


class AppPaths:
    def __init__(self, base_dir: str):
        self.BASE_DIR = base_dir

        self.UPLOAD_FOLDER = os.path.join(base_dir, "uploads")
        self.PROCESSED_FOLDER = os.path.join(base_dir, "processed")
        self.PREVIEW_FOLDER = os.path.join(base_dir, "previews")
        self.EXPORT_FOLDER = os.path.join(base_dir, "exports")
        self.ASSETS_FOLDER = os.path.join(base_dir, "assets")
        self.TEMPLATES_FOLDER = os.path.join(base_dir, "templates")

        self.CONFIG_PATH = os.path.join(base_dir, "config.json")
        self.TEMPLATES_CONFIG_PATH = os.path.join(base_dir, "templates_config.json")

    def ensure_dirs(self) -> None:
        for folder in [
            self.UPLOAD_FOLDER,
            self.PROCESSED_FOLDER,
            self.PREVIEW_FOLDER,
            self.EXPORT_FOLDER,
            self.ASSETS_FOLDER,
            self.TEMPLATES_FOLDER,
        ]:
            os.makedirs(folder, exist_ok=True)