from __future__ import annotations

import dataclasses
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class DBStatus:
    """
    The status of a postgres database.
    """

    pg_data: Path
    logfile: Path
    port: int
    running: bool
    pid: int | None
