"""Deterministic OpenAPI Schema Generator for RegulatorIQ.

Dumps OpenAPI JSON from the FastAPI application factory to docs/openapi.json
with sorted keys and clean formatting for frontend codegen and contract testing.
"""

from __future__ import annotations

import json

from api.main import create_app
from api.settings import APISettings
from config.paths import OPENAPI_PATH


def generate_openapi_json() -> None:
    """Generate and write docs/openapi.json."""
    # Force DOCS_ENABLED=1 so openapi() compiles all schemas
    settings = APISettings(DOCS_ENABLED=1, ALLOW_DOCS_IN_PROD=1, ENV="dev")
    app = create_app(settings)
    schema = app.openapi()

    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENAPI_PATH, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, sort_keys=True)
    print(f"✅ Generated OpenAPI schema at {OPENAPI_PATH}")


if __name__ == "__main__":
    generate_openapi_json()
