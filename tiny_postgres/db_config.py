from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class DBConfig:
    """
    The configuration of a postgres database.
    This is used to initialize a database.
    """

    pg_data: Path | None = dataclasses.field(
        default_factory=lambda: Path(tempfile.mkdtemp())
    )
    logfile: Path | None = dataclasses.field(
        default_factory=lambda: Path(tempfile.mktemp(suffix=".log"))
    )
    port: int = 5432
    delete_on_exit: bool = True

    @property
    def pidfile(self) -> Path:
        return self.pg_data / "postmaster.pid"

    def __post_init__(self):
        self.pg_data.mkdir(parents=True, exist_ok=True)
        self.logfile.touch(exist_ok=True)
