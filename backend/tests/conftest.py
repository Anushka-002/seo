import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["EMBEDDER"] = "hashing"
os.environ["SERPER_API_KEY"] = ""

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.main import app  # noqa: E402

PAGES_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "pages"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def settings() -> Settings:
    return Settings(serper_api_key="test-key", embedder="hashing", database_url="sqlite://")


@pytest.fixture
def pages_html() -> dict[str, str]:
    """domain -> html for the 6 sample pages (5 good, 1 thin)."""
    return {f.stem: f.read_text(encoding="utf-8") for f in sorted(PAGES_DIR.glob("*.html"))}
