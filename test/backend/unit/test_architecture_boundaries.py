from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3] / "backend" / "app"


def _python_files(package: str):
    return (APP_ROOT / package).rglob("*.py")


def test_application_and_service_layers_do_not_import_api_modules():
    offenders = []
    forbidden = ("from ..api", "from app.api", "import app.api", "..api.")

    for package in ("application", "services"):
        for path in _python_files(package):
            text = path.read_text(encoding="utf-8")
            if any(pattern in text for pattern in forbidden):
                offenders.append(str(path.relative_to(APP_ROOT)))

    assert offenders == []


def test_domain_layer_does_not_import_persistence_or_infrastructure_modules():
    offenders = []
    forbidden = (
        "from ..models",
        "from app.models",
        "import app.models",
        "from ..event_bus",
        "from app.event_bus",
        "import app.event_bus",
        "from ..services",
        "from app.services",
        "import app.services",
    )

    for path in _python_files("domain"):
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in forbidden):
            offenders.append(str(path.relative_to(APP_ROOT)))

    assert offenders == []
