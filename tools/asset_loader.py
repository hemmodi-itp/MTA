import os
from typing import Any, Dict

from tools.file_manager import load_json_file, load_yaml_file


def base_asset_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "application_assets"))


def load_target_application_config(project_name: str = "countrydelight") -> Dict[str, Any]:
    path = os.path.join(base_asset_dir(), "projects", project_name, "project.yaml")
    return load_yaml_file(path)


def ui_assets_dir(project_name: str = "countrydelight") -> str:
    return os.path.join(base_asset_dir(), "projects", project_name, "ui")


def locator_dir() -> str:
    return os.path.join(ui_assets_dir(), "locators")


def page_dir() -> str:
    return os.path.join(ui_assets_dir(), "pages")


def intent_dir() -> str:
    return os.path.join(ui_assets_dir(), "intents")


def scenario_dir() -> str:
    return os.path.join(ui_assets_dir(), "scenarios")
