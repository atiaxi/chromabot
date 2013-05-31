
from db import User
from utils import num_to_team


class Context(object):
    def __init__(self, player, config, session, comment):
        self.player = player    # a DB object
        self.config = config
        self.session = session
        self.comment = comment  # a praw object


class Command(object):

    FAIL_NOT_PLAYER = """
Sorry, I can't help you - first of all, you messaged a bot.  Secondly, you
don't seem to actually be playing the game I run!  If you'd like to change
that, comment in the latest recruitment thread in /r/%s"""

    def __init__(self, tokens):
        self.tokens = tokens

    def execute(self, context):
        pass


class StatusCommand(Command):

    def execute(self, context):
        status = self.status_for(context)
        context.comment.reply(status)

    def status_for(self, context):
        found = context.player
        result = """
You are a general in the %s army.

Your forces number %d loyalists strong.

You are currently encamped at [%s](/r/%s).
""" % (num_to_team(found.team), found.loyalists, found.region.name,
       found.region.srname)
        return result


class MoveCommand(Command):
    def __init__(self, tokens):
        self.amount = int(tokens["amount"])
        self.where = tokens["where"]

    def __repr__(self):
        return "<MoveCommand(amount='%s', where='%s')>" % (
            self.amount, self.where)
