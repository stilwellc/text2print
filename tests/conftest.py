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

import pytest


@pytest.fixture(autouse=True)
def _studio_test_client_is_local():
    """The studio only answers its own page: a request with no port in Host (Flask's test client) is let in only when
    app.testing is set. One test file set the flag and the others relied on it having run first, so a studio test run
    on its own got 403. Set it for every test."""
    try:
        from studio import server
    except ImportError:                                         # no flask: the studio tests skip themselves
        yield
        return
    was = server.app.testing
    server.app.testing = True
    yield
    server.app.testing = was
