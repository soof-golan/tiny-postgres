from __future__ import annotations

import getpass
import logging
import os
import re
import shutil
import signal
import subprocess
from contextlib import contextmanager
from typing import Generator

import pg8000.dbapi
from retry import retry

from tiny_postgres.db_status import DBStatus
from tiny_postgres.db_config import DBConfig
from tiny_postgres.env import get_pg_environ, get_postgres_bin_dir

logger = logging.getLogger(__name__)


class TinyPostgres:
    def __init__(self, config: DBConfig):
        self.config = config
        self.bin_dir = get_postgres_bin_dir()
        self.subprocess_kwargs = {
            "env": get_pg_environ(),
            "universal_newlines": True,
            "check": True,
            "capture_output": True,
            "timeout": 10,
        }

    def _run(self, args: list[str]):
        """
        Run a pg_ctl command.
        :param args: The arguments to pass to pg_ctl.
        :return: The context of the pg_ctl command.
        """
        result = subprocess.run(
            [str(self.bin_dir / "pg_ctl"), *args],
            **self.subprocess_kwargs,
        )
        return self._handle_result(result)

    def _handle_result(self, result) -> str:
        """
        Handle the result of a pg_ctl command.
        :param result: The result of the pg_ctl command.
        :return:
        """
        if result.returncode != 0:
            logger.error(result.stderr)
            raise RuntimeError(
                f"pg_ctl failed with code {result.returncode}: {result.stderr}"
            )
        logger.debug(result.stdout)
        return result.stdout

    def initdb(self) -> str:
        """
        Initialize a postgres database using pg_ctl.
        :return: The context of the initialized database.
        """
        logger.debug(f"Initializing database at {self.config.pg_data}")
        return self._run(["initdb", "-D", str(self.config.pg_data)])

    def start(self) -> str:
        """
        Start a postgres database using pg_ctl.
        :return: The context of the started database.
        """
        logger.debug(f"Starting database at {self.config.pg_data}")
        return self._run(
            [
                "start",
                "-D",
                str(self.config.pg_data),
                "-l",
                str(self.config.logfile),
                "-o",
                f"-p {self.config.port}",
            ]
        )

    @retry(RuntimeError, tries=3, delay=1)
    def stop(self) -> str:
        """
        Stop a postgres database using pg_ctl.
        :return: The context of the stopped database.
        """
        logger.debug(f"Stopping database at {self.config.pg_data}")
        return self._run(["stop", "-D", str(self.config.pg_data)])

    def status(self) -> DBStatus:
        """
        Get the status of a postgres database using pg_ctl.
        :return: The status of the database.
        """
        logger.debug(f"Getting status of database at {self.config.pg_data}")
        out = self._run(["status", "-D", str(self.config.pg_data)])
        pattern = re.compile(
            r"^pg_ctl: server is running \(PID: (?P<pid>\d+)\).*",
            re.MULTILINE | re.IGNORECASE,
        )
        status = pattern.match(out)
        pid = int(status.group("pid")) if status else None
        is_running = "server is running" in out
        return DBStatus(
            running=is_running,
            pid=pid,
            port=self.config.port,
            pg_data=self.config.pg_data,
            logfile=self.config.logfile,
        )

    def kill(self) -> DBStatus:
        """
        Kill a postgres database using pg_ctl.
        :return: The context of the killed database.
        """
        status = self.status()
        if status.pid is None:
            return status
        logger.info(f"Killing database at {self.config.pg_data}")
        self._run(["kill", "KILL", str(status.pid)])
        if self.config.pidfile.exists():
            pid = int(self.config.pidfile.read_text())
            os.kill(pid, signal.SIGKILL)
        status = self.status()
        return status

    @retry(pg8000.Error, tries=10, delay=0.1, backoff=2, logger=logger, max_delay=5)
    def _connect(self) -> pg8000.dbapi.Connection:
        return pg8000.dbapi.connect(
            user=getpass.getuser(),
            host="localhost",
            port=self.config.port,
            database="postgres",
        )

    def _test_connection(self) -> None:
        """
        Test the connection to a postgres server.
        """
        try:
            connection = self._connect()
            connection.close()
        except pg8000.Error as e:
            logger.exception("Failed to connect to postgres server", exc_info=e)
            raise

    def _cleanup(self) -> None:
        """
        Remove the postgres data directory.
        """
        if self.config.delete_on_exit:
            logger.debug(f"Cleaning up postgres data directory {self.config.pg_data}")
            shutil.rmtree(self.config.pg_data, ignore_errors=True)

    def __enter__(self) -> TinyPostgres:
        self.initdb()
        self.start()
        self._test_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.stop()
            pg_data_cleanup(self.config)
        except RuntimeError:
            self.kill()
            self._cleanup()


@retry(pg8000.Error, tries=10, delay=0.1, backoff=2, logger=logger, max_delay=5)
def connect(ctx: DBConfig) -> pg8000.dbapi.Connection:
    return pg8000.dbapi.connect(
        user=getpass.getuser(),
        host="localhost",
        port=ctx.port,
        database="postgres",
    )


def test_connection(ctx: DBConfig) -> None:
    """
    Test the connection to a postgres server.

    :param ctx: The database context.
    """
    logger.debug(f"Testing connection to postgres server on port {ctx.port}")
    conn = connect(ctx)
    logger.debug(f"successfully connected to postgres server {conn=}")
    conn.close()
    logger.debug(f"Connection to postgres server on port {ctx.port} successful")


def pg_data_cleanup(db_config: DBConfig):
    """
    Cleanup the postgres data directory.
    :param db_config: The database configuration.
    :return:
    """
    if db_config.delete_on_exit:
        logger.debug(f"Cleaning up postgres data directory {db_config.pg_data}")
        shutil.rmtree(db_config.pg_data, ignore_errors=True)


@contextmanager
def postgres(config: DBConfig) -> Generator[TinyPostgres, None, None]:
    status: DBStatus | None = None
    pg_ctl = TinyPostgres(config)
    try:
        logger.debug(
            f"Starting postgres server on port {config.port}, data dir {config.pg_data}"
        )
        pg_ctl.initdb()
        pg_ctl.start()
        test_connection(config)
        status = pg_ctl.status()
        logger.debug(f"postgres server status: {status}")
        yield pg_ctl
    finally:
        try:
            pg_ctl.stop()
        except RuntimeError:
            pg_ctl.kill()
            if pg_ctl.config.pidfile.exists():
                pid = int(config.pidfile.read_text())
                os.kill(pid, signal.SIGKILL)
        if config.delete_on_exit:
            logger.debug(f"Cleaning up postgres data directory {config.pg_data}")
            shutil.rmtree(config.pg_data, ignore_errors=True)
