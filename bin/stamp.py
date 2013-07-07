#!/usr/bin/env python

from alembic.config import Config
from alembic import command

def stamp():
    alembic_cfg = Config("alembic.ini")
    command.stamp(alembic_cfg, "head")


if __name__ == '__main__':
    stamp()
