import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# the suite never sees the user's own plugins or picture library (they'd make results machine-dependent)
import os
import tempfile

_EMPTY = tempfile.mkdtemp(prefix="t2p_test_")
os.environ.setdefault("T2P_PLUGINS", os.path.join(_EMPTY, "plugins"))
os.environ.setdefault("T2P_PICTURES", os.path.join(_EMPTY, "pictures"))
