"""Entry point for Sony RAW to JPG Converter."""
from __future__ import annotations

import sys
from pathlib import Path

# Make the ``src`` packages importable both from source and from a PyInstaller bundle.
_HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(_HERE / "src"))

from bootstrap import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
