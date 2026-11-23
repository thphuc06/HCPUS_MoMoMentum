"""Thêm pipeline Lambda vào đường dẫn import của các unit test."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def roadmap_import_path():
    root = Path(__file__).resolve().parents[3]
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(root / "pipelines" / "roadmap"))
        yield
