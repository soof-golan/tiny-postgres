from __future__ import annotations

import os
from pathlib import Path


def get_postgres_dir() -> Path:
    """
    Get the path to the build directory.

    :return: The path to the build directory.
    """
    return Path(__file__).parent / "_postgres"


def get_postgres_bin_dir() -> Path:
    """
    Get the path to the postgres binaries.

    :return: The path to the postgres binaries.
    """
    return get_postgres_dir() / "bin"


def get_postgres_lib_dir() -> Path:
    """
    Get the path to the postgres libraries.

    :return: The path to the postgres libraries.
    """
    return get_postgres_dir() / "lib"


def get_pg_environ():
    environ = {
        **os.environ,
        "LD_LIBRARY_PATH": str(get_postgres_lib_dir()),
        "DYLD_LIBRARY_PATH": str(get_postgres_lib_dir()),
        "PATH": os.environ["PATH"] + ":" + str(get_postgres_bin_dir()),
    }
    return environ
