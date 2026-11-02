import os
from pathlib import Path

# Tests run on the small sample in tests/fixtures/data.
os.environ.setdefault("IDEATASTE_DATA", str(Path(__file__).parent / "fixtures" / "data"))
