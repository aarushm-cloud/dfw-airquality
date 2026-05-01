"""Write the FastAPI OpenAPI schema to a versioned snapshot file.

Run manually whenever you want a fresh contract baseline:

    python api/scripts/snapshot_openapi.py

Diffing the resulting api/openapi.snapshot.json across commits surfaces any
unintended API contract changes.
"""

import json
import sys
from pathlib import Path

# Allow `python api/scripts/snapshot_openapi.py` from the project root by
# prepending the repo root onto sys.path before importing the app package.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.main import app  # noqa: E402


def main() -> None:
    out_path = Path(__file__).resolve().parent.parent / "openapi.snapshot.json"
    schema = app.openapi()
    out_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"OpenAPI snapshot written to {out_path}")


if __name__ == "__main__":
    main()
