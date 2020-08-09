# February 2020, Lewis Gaul

"""
Bot package.

"""

__all__ = ("init_route_handling",)

import logging
import os
import sys

import flask

from server import add_new_highscore_hook

from . import msgparse, routes, utils


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# External
# ------------------------------------------------------------------------------


def init_route_handling(app: flask.app.Flask):
    if "BOT_ACCESS_TOKEN" not in os.environ:
        logger.error("No 'BOT_ACCESS_TOKEN' env var set")
        sys.exit(1)
    utils.set_bot_access_token(os.environ["BOT_ACCESS_TOKEN"])

    utils.read_users_file()

    routes.activate_bot_msg_handling(app)

    add_new_highscore_hook(routes.new_highscore_hook)
