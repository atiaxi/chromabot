
import db
from db import Region, User
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
        self.where = tokens["where"].lower()

    def execute(self, context):
        dest = context.session.query(Region).filter_by(name=self.where).first()
        if not dest:
            dest = context.session.query(Region).filter_by(
                srname=self.where).first()
        if dest:
            order = None
            try:
                speed = context.config["game"]["speed"]
                hundred_followers = self.amount / 100
                time_taken = speed * hundred_followers

                order = context.player.move(self.amount, dest, time_taken)
            except db.InsufficientException as ie:
                context.comment.reply(
                    "You cannot move %d of your people - you only have %d" %
                    (ie.requested, ie.available))
                return
            except db.NonAdjacentException:
                context.comment.reply(
                    "Your current region, %s, is not adjacent to %s" %
                    (context.player.region.markdown(), dest.markdown()))
                return
            except db.AlreadyMovingException as ame:
                context.comment.reply((
                    "You are already leading your armies to %s - "
                    "you can give further orders upon your arrival at %s"
                    ) % (ame.order.dest.markdown(), ame.order.arrival_str()))
                return
            if order:
                context.comment.reply((
                    "**Confirmed**: You are leading %d of your people to %s. "
                    "You will arrive at %s."
                    ) % (self.amount, dest.markdown(), order.arrival_str()))
            else:
                context.comment.reply((
                    "**Confirmed**: You have lead %d of your people to %s."
                    ) % (self.amount, dest.markdown()))
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

        moving = context.player.is_moving()
        if moving:
            forces = ("Your forces are currently on the march to %s "
                      "and will arrive at %s")
            forces = forces % (moving.dest.markdown(), moving.arrival_str())
        else:
            forces = ("You are currently encamped at %s" %
                      found.region.markdown())

        result = ("You are a %s in the %s army.\n\n"
                  "Your forces number %d loyalists strong.\n\n"
                  "%s")
        return result % (found.rank, num_to_team(found.team), found.loyalists,
                         forces)
