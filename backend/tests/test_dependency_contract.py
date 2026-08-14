import tomllib
from pathlib import Path


def test_webauthn_is_pinned_to_the_production_compatible_version() -> None:
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))

    assert "webauthn==2.8.0" in pyproject["project"]["dependencies"]
