import os
import stat

import pytest

from backend.database import Database


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes required")
def test_database_restricts_new_and_existing_file_modes(tmp_path):
    path = tmp_path / "sensitive.db"
    Database(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o666)
    Database(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
