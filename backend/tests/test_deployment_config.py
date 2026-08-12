import runpy
import warnings
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import Response

from app import run
from app.core.config import BACKEND_ROOT, PROJECT_ROOT, Settings
from app.main import create_app


def cors_response(settings: Settings, origin: str) -> Response:
    with TestClient(create_app(settings)) as client:
        return client.options(
            "/api/v1/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )


def test_environment_files_are_absolute_and_independent_of_working_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    env_files = tuple(Path(path) for path in Settings.model_config["env_file"])

    assert env_files == (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env")
    assert all(path.is_absolute() for path in env_files)


def test_local_cors_allows_private_network_development() -> None:
    settings = Settings(frontend_origin="http://localhost:5173", cors_allow_local_network=True)
    response = cors_response(settings, "http://192.168.0.15:5173")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.0.15:5173"

    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/health")
    assert health.json() == {"status": "ok"}


def test_production_cors_only_allows_the_configured_origin() -> None:
    settings = Settings(frontend_origin="http://bca.iptime.org", cors_allow_local_network=False)
    allowed = cors_response(settings, "http://bca.iptime.org")
    rejected = cors_response(settings, "http://192.168.0.15:5173")
    assert allowed.headers["access-control-allow-origin"] == "http://bca.iptime.org"
    assert "access-control-allow-origin" not in rejected.headers


def test_server_runner_uses_environment_host_port_and_proxy_settings(monkeypatch) -> None:
    settings = Settings(
        app_host="127.0.0.1",
        app_port=8000,
        app_debug=False,
        proxy_trusted_ips="127.0.0.1",
    )
    captured: dict[str, object] = {}

    def fake_run(application: str, **kwargs: object) -> None:
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr(run, "get_settings", lambda: settings)
    monkeypatch.setattr(run, "revoke_active_sessions", lambda: captured.update(sessions_revoked=True))
    monkeypatch.setattr(run.uvicorn, "run", fake_run)
    run.main()

    assert captured == {
        "application": "app.main:app",
        "host": "127.0.0.1",
        "port": 8000,
        "reload": False,
        "proxy_headers": True,
        "forwarded_allow_ips": "127.0.0.1",
        "sessions_revoked": True,
    }


def test_module_entrypoint_uses_the_same_runner(monkeypatch) -> None:
    settings = Settings(app_host="0.0.0.0", app_port=9123, app_debug=True)
    captured: dict[str, object] = {}
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.auth.revoke_active_sessions", lambda: None)
    monkeypatch.setattr("uvicorn.run", lambda application, **kwargs: captured.update(application=application, **kwargs))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("app.run", run_name="__main__")

    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9123
    assert captured["reload"] is True


def test_request_context_returns_a_sanitized_500_response() -> None:
    application = create_app(Settings())

    @application.get("/boom")
    def boom() -> None:
        raise RuntimeError("sensitive failure")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"x-request-id": "known-request"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "known-request"}
    assert response.headers["x-request-id"] == "known-request"
