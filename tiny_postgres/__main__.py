import logging

import typer

from tiny_postgres import TinyPostgres
from tiny_postgres.db_config import DBConfig

app = typer.Typer()

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("tiny_postgres")
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def main():
    app()


@app.command()
def start(port: int = 5432, rm: bool = False):
    config = DBConfig(port=port, delete_on_exit=rm)
    with TinyPostgres(config) as pg:
        status = pg.status()
        typer.echo(status)
        typer.prompt("Press q to exit")


if __name__ == "__main__":
    main()
