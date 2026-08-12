import pytest


@pytest.fixture(autouse=True)
def isolate_global_app_startup_from_the_development_database():
    """Keep TestClient(app) from revoking sessions in the developer's real database."""
    from app.main import app

    app.state.disable_startup_session_revocation = True
    yield
    app.state.disable_startup_session_revocation = False
