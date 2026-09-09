"""Shared test setup.

The test suite must never write to the development `inspections.db`. The
DATABASE_URL is redirected to a per-run temporary SQLite file *before*
`backend.app.database` is imported anywhere, because that module reads the
env var at import time.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TEST_DB = Path(tempfile.gettempdir()) / "labelguard_test_inspections.db"
if _TEST_DB.exists():
    try:
        _TEST_DB.unlink()
    except OSError:
        pass
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
# Auth enforcement is opt-in; tests that need it enable it explicitly.
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-not-for-production")

# No test may call a paid API or depend on whether a developer happens to have
# a key in .env. Importing the app loads .env, so this is cleared here and the
# generation path is exercised with stubs instead.
os.environ.pop("GROQ_API_KEY", None)
os.environ["LABELSURE_DISABLE_DOTENV"] = "1"

import pytest


@pytest.fixture
def sample_result():
    """A representative multi-surface inspection result, produced by the real
    pipeline with OCR and the quality gate stubbed."""
    from backend.app.services.pipeline import InspectionPipeline

    pipeline = InspectionPipeline(annotate=False)
    front = [
        "ACME(TM)",
        "CRISPY WAFERS",
        "MRP: Rs. 45.00",
        "Net Qty: 200 g",
    ]
    back = [
        "Manufactured By: ABC Foods Pvt Ltd",
        "Plot 5, MIDC, Pune 411001",
        "Mfg Date: 01/2026",
        "Best Before: 12 Months",
        "Customer Care: 1800-200-1234",
        "care@abcfoods.com",
        "Ingredients: wheat flour, salt",
        "Country of Origin: India",
    ]

    def fake_ocr(path):
        texts = front if "front" in path else back
        return {
            "texts": texts,
            "confidences": [0.97] * len(texts),
            "bounding_boxes": [
                [[10, i * 60], [300, i * 60], [300, i * 60 + 40], [10, i * 60 + 40]]
                for i in range(len(texts))
            ],
            "avg_confidence": 0.97,
        }

    pipeline.assess_quality = lambda path: {"usable": True, "score": 94.0, "checks": {}}
    pipeline.ocr = fake_ocr
    return pipeline.run_multi(
        ["x_front.jpg", "y_back.jpg"],
        image_names=["front.jpg", "back.jpg"],
        product_name="Crispy Wafers 200g",
    )
