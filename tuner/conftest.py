"""Root conftest: set TUNER_DB to a temp path before any imports touch /data."""

import atexit
import os
import tempfile

# Must happen before api.db is imported so init_db() uses the tmp path.
_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
atexit.register(os.unlink, _tmp_db_path)
os.environ["TUNER_DB"] = _tmp_db_path
os.environ["TUNER_USER"] = "test-user"
os.environ["TUNER_PASSWORD"] = "test-password"
