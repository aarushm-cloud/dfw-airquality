"""
Test configuration: ensure the project root is on sys.path so tests can
import `data.corrections`, `data.ingestion.history`, etc. without the
caller having to install the package.
"""
import sys
from pathlib import Path

# tests/ lives one level under the repo root
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
