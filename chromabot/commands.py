
from db import InsufficientException, NonAdjacentException, Region, User
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


class MoveCommand(Command):
    def __init__(self, tokens):
        self.amount = int(tokens["amount"])
        self.where = tokens["where"]

    def execute(self, context):
        dest = context.session.query(Region).filter_by(name=self.where).first()
        if not dest:
            dest = context.session.query(Region).filter_by(
                srname=self.where).first()
        if dest:
            try:
                context.player.move(self.amount, dest, 0)
            except InsufficientException as ie:
                context.comment.reply("""
You cannot move %d of your people - you only have %d""" % (ie.requested,
                                                           ie.available))
                return
            except NonAdjacentException as nae:
                context.comment.reply("""
Your current region, %s, is not adjacent to %s
""" % (context.player.region.markdown(), dest.markdown()))
                return
            context.comment.reply("""
Confirmed: Your are leading %d of your people to [%s](/r/%s).  You will arrive
in %d seconds.""" % (self.amount, dest.name, dest.srname, 0))

        else:
            context.comment.reply(
                "I don't know any region or subreddit named '%s'" %
                self.where)

    def __repr__(self):
        return "<MoveCommand(amount='%s', where='%s')>" % (
            self.amount, self.where)


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

