import logging
import re
import time
import traceback

import praw
from requests.exceptions import ConnectionError, HTTPError, Timeout

import db
from db import Battle, Region, Processed, SkirmishAction, User
from utils import now, num_to_team, team_to_num, timestr


def failable(f):
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except praw.errors.APIException:
            full = traceback.format_exc()
            logging.warning("Reddit API call failed! %s" % full)
            return None
        except ConnectionError:
            full = traceback.format_exc()
            logging.warning("Connection error: %s", full)
        except Timeout:
            full = traceback.format_exc()
            logging.warning("Socket timeout! %s" % full)
            return None
        except HTTPError:
            full = traceback.format_exc()
            logging.warning("HTTP error timeout! %s" % full)
            return None
    return wrapped


class Context(object):
    def __init__(self, player, config, session, comment, reddit):
        self.player = player    # a DB object
        self.config = config
        self.session = session
        self.comment = comment  # a praw object
        self.reddit = reddit    # root praw object

    @failable
    def reply(self, reply, pm=True):
        was_comment = getattr(self.comment, 'was_comment', True)
        header = ""
        if was_comment and pm:
            header = ("(In response to [this comment](%s))" %
                      self.comment.permalink)
        else:  # It wasn't a comment, or pm = False
            return self.comment.reply(reply)

        full_reply = "%s\n\n%s" % (header, reply)
        self.reddit.send_message(self.player.name, "Chromabot reply",
                                 full_reply)

    @failable
    def submit(self, srname, title, text):
        return self.reddit.submit(srname, title=title, text=text)

    def team_name(self):
        return num_to_team(self.player.team, self.config)


class Command(object):

    FAIL_NOT_PLAYER = """
Sorry, I can't help you - first of all, you messaged a bot.  Secondly, you
don't seem to actually be playing the game I run!  If you'd like to change
that, comment in the latest recruitment thread in /r/%s"""

    def __init__(self, tokens):
        self.tokens = tokens

    def execute(self, context):
        raise NotImplementedError()

    # Helper functions for subclasses
    def get_region(self, where, context, require=True):
        sess = context.session
        dest = sess.query(Region).filter_by(name=where).first()
        if not dest:
            dest = sess.query(Region).filter_by(
                srname=where).first()
        if require and not dest:
            context.reply(
                "I don't know any region or subreddit named '%s'" %
                self.where)
        return dest


class CodewordCommand(Command):
    def __init__(self, tokens):
        self.remove = 'remove' in tokens
        self.all = 'all' in tokens
        self.status = 'status' in tokens
        if 'code' in tokens:
            self.code = tokens['code']
        self.word = tokens.get('troop_type', 'infantry')
        # Correct spelling
        self.word = SkirmishCommand.ALIASES.get(self.word, self.word)

    def execute(self, context):
        if self.remove:
            if self.all:
                cws = list(context.player.codewords)
                for cw in cws:
                    context.session.delete(cw)
                context.session.commit()
                context.reply("**Confirmed**:  You no longer have codewords")
            else:
                context.player.remove_codeword(self.code)
                context.reply("**Confirmed**:  %s is no longer a codeword" %
                              self.code)
        elif self.status:
            context.reply("Your codewords are as follows:\n\n%s" %
                          "\n\n".join(self.status_list(context)))
        else:
            context.player.add_codeword(self.code, self.word)
            context.reply(("**Confirmed**:  `%s` will now refer to %s") %
                          (self.code, self.word))

    def status_list(self, context):
        result = ["**%s**: `%s`" % (cw.word, cw.code)
                  for cw in context.player.codewords]
        return result


class DefectCommand(Command):
    def __init__(self, tokens):
        self.team = None
        if "team" in tokens:
            self.team = team_to_num(tokens["team"])

    def execute(self, context):
        if self.team is None:
            self.team = [0, 1][context.player.team - 1]
        try:
            context.player.defect(self.team)
            context.reply(("Done - you are now on team %s and encamped"
                                  " in their capital of %s") %
                                  (context.team_name(),
                                  context.player.region.markdown()))
        except db.TeamException:
            context.reply("You're trying to defect to the team you're "
                                  "already on!")
        except db.TimingException:
            context.reply("You can only defect if you haven't taken "
                                  "any actions.")


class InvadeCommand(Command):
    def __init__(self, tokens):
        self.where = tokens["where"].lower()

    @staticmethod
    @failable
    def post_invasion(title, battle, reddit):
        text = ("Negotiations have broken down, and the trumpets of "
                "war have sounded.  Even now, civilians are being "
                "evacuated and the able-bodied drafted.  The conflict "
                "will soon be upon you.\n\n"
                "Gather your forces while you can, for your enemy "
                "shall arrive at %s") % battle.begins_str()
        submitted = reddit.submit(battle.region.srname,
                                   title=title,
                                   text=text)
        return submitted

    def execute(self, context):
        dest = self.get_region(self.where, context)
        if dest:
            now = time.mktime(time.localtime())
            begins = now + context.config["game"]["battle_delay"]
            battle = None

            if dest.capital is not None:
                invade = context.config['game']['capital_invasion']
                if invade == 'none':
                    context.reply("You cannot invade the enemy capital")
                    return

            try:
                battle = dest.invade(context.player, begins)
                if "battle_lockout" in context.config["game"]:
                    battle.lockout = context.config["game"]["battle_lockout"]
                    context.session.commit()
            except db.RankException:
                context.reply("You don't have the authority "
                              "to invade a region!")
            except db.TeamException:
                context.reply("You can't invade %s, you already own it!" %
                              dest.markdown())
            except db.NonAdjacentException:
                context.reply("%s is not next to any territory you control" %
                              dest.markdown())
            except db.InProgressException as ipe:
                context.reply("%s is %s being invaded!" % (dest.markdown(),
                              ipe.other.markdown("already")))

            if battle:
                context.reply("**Confirmed**  Battle will begin at %s" %
                              battle.begins_str())
                title = ("[Invasion] The %s armies march!" %
                 context.team_name())
                submitted = InvadeCommand.post_invasion(title, battle,
                                                        context.reddit)
                if submitted:
                    battle.submission_id = submitted.name
                    context.session.commit()
                else:
                    logging.warn("Couldn't submit invasion thread")
                    context.session.rollback()


class MoveCommand(Command):
    def __init__(self, tokens):
        if "amount" in tokens:
            self.amount = int(tokens["amount"])
        else:
            self.amount = -1
        self.where = tokens["where"].lower()

    def execute(self, context):
        dest = self.get_region(self.where, context)
        if dest:
            order = None

            if self.amount == -1:  # -1 means 'everyone'
                self.amount = context.player.loyalists

            try:
                speed = context.config["game"]["speed"]
                #hundred_followers = self.amount / 100
                time_taken = speed  # * hundred_followers

                order = context.player.move(self.amount, dest, time_taken)
            except db.InsufficientException as ie:
                context.reply(
                    "You cannot move %d of your people - you only have %d" %
                    (ie.requested, ie.available))
                return
            except db.NonAdjacentException:
                text = ("Your current region, %s, is not adjacent to %s" %
                    (context.player.region.markdown(), dest.markdown()))
                if context.player.region == dest:
                    text = ("How can you go to %s when "
                            "you are *already here*?") % dest.markdown()
                context.reply(text)

                return
            except db.InProgressException as ipe:
                # Determine if there's a move in progress or a battle
                if hasattr(ipe.other, 'arrival_str'):
                    context.reply((
                        "You are already leading your armies to %s - "
                        "you can give further orders upon your arrival at %s"
                        ) % (ipe.other.dest.markdown(),
                             ipe.other.arrival_str()))
                else:
                    context.reply((
                        "You have committed your armies to the battle at %s - "
                        "you must see this through to the bitter end."
                        ) % (ipe.other.get_battle().region.markdown()))
                return
            except db.TeamException:
                context.reply(("%s is not friendly territory - invade first "
                               "if you want to go there") % self.where)
                return
            context.player.defectable = False
            if order:
                context.reply((
                    "**Confirmed**: You are leading %d of your people to %s. "
                    "You will arrive at %s."
                    ) % (self.amount, dest.markdown(), order.arrival_str()))
            else:
                context.reply((
                    "**Confirmed**: You have lead %d of your people to %s."
                    ) % (self.amount, dest.markdown()))
            context.session.commit()

    def __repr__(self):
        return "<MoveCommand(amount='%s', where='%s')>" % (
            self.amount, self.where)


class StatusCommand(Command):

    def execute(self, context):
        status = self.status_for(context)
        context.reply(status)

    def lands_status(self, context):
        regions = context.session.query(Region).all()
        fmt = "* **%s**:  %s%s"
        result = []
        for region in regions:
            dispute = ""
            if region.battle:
                dispute = " ( %s )" % region.battle.markdown()
            result.append(fmt % (region.markdown(),
                                 num_to_team(region.owner, context.config),
                                 dispute))
        lands = "\n".join(result)
        return "State of Chroma:\n\n" + lands

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

        commit_str = ""
        if found.committed_loyalists:
            commit_str = (", %d of which are committed to battle" %
                          found.committed_loyalists)
        result = ("You are a %s in the %s army.\n\n"
                  "Your forces number %d loyalists%s.\n\n"
                  "%s")
        personal = result % (found.rank, context.team_name(),
                             found.loyalists, commit_str, forces)
        return personal + "\n\n" + self.lands_status(context)


class PromoteCommand(Command):
    def __init__(self, tokens):
        self.who = tokens["who"]
        if tokens["direction"] == "promote":
            self.direction = 1
        else:
            self.direction = 0
        self.direction_str = tokens["direction"]

    def execute(self, context):
        person = context.session.query(User).filter_by(name=self.who).first()
        if person:
            if context.player.leader:
                person.leader = self.direction
                context.reply("%s has been %sd!" % (self.who,
                                                    self.direction_str))
                context.session.commit()
            else:
                context.reply("You can't promote if you aren't a leader "
                              "yourself!")
        else:
            context.reply("I don't know who %s is" % self.who)


class SkirmishCommand(Command):

    ALIASES = {
        "calvalry": "cavalry",
        "calvary":  "cavalry",
        "range":    "ranged"
    }

    def __init__(self, tokens):
        self.action = self.ALIASES.get(tokens['action'], tokens['action'])
        if self.action == 'oppose':  # Clearer-sounding synonym for 'attack'
            self.action = 'attack'
        self.amount = int(tokens['amount'])
        self.troop_type = 'infantry'
        if 'troop_type' in tokens:
            self.troop_type = SkirmishCommand.ALIASES.get(tokens['troop_type'],
                                                          tokens['troop_type'])
        self.target = None
        if "target" in tokens:
            self.target = int(tokens['target'])

    def execute(self, context):
        # getattr wackiness because real comments not gotten from inbox don't
        # have "was_comment" set on them
        if not getattr(context.comment, 'was_comment', True):
            # PMing skirmish commands makes no sense
            context.reply("You must enter your skirmish commands in the "
                          "appropriate battle post")
            return

        post_id = context.comment.link_id  # Actually a 'name'
        ongoing = context.session.query(Battle).filter_by(
            submission_id=post_id)
        current = ongoing.first()
        if not current:
            context.reply("There's no battle happening here!")
            return

        try:
            if not self.target and post_id == context.comment.parent_id:
                skirmish = current.create_skirmish(context.player, self.amount,
                                                   troop_type=self.troop_type)
            else:
                if self.target:
                    parent = self.find_skirmish_by_id(self.target, context)
                    if parent and parent.battle != current:
                        context.reply("That skirmish belongs to "
                                      "another battle!")
                        return
                    if not parent:
                        context.reply("That does not appear to be a valid "
                                      "skirmish!")
                        return
                else:
                    parent = self.find_skirmish_named(
                        context.comment.parent_id, context)
                if not parent:
                    sub = self.extract_subskirmish(context, current)
                    if sub:
                        parent = self.find_skirmish_by_id(sub, context)
                    if not parent:
                        context.reply("You can only use skirmish commands in "
                                      "reply to other confirmed skirmish "
                                      "commands")
                        return
                hinder = self.action == 'attack'
                skirmish = parent.react(context.player, self.amount,
                                        hinder=hinder,
                                        troop_type=self.troop_type)
            total = context.player.committed_loyalists

            subskirmish = ""
            if skirmish.get_root().id != skirmish.id:
                subskirmish = " (subskirmish %d)" % skirmish.id

            context.reply(("**Confirmed**: You have committed %d of your "
                "forces as **%s** to **Skirmish #%d**%s.\n\nAs of now, you "
                "have committed %d total.  **For %s!**") %
                          (skirmish.amount,
                           skirmish.troop_type,
                           skirmish.get_root().id,
                           subskirmish,
                           total, context.team_name()))

            skirmish.comment_id = context.comment.name
            if not skirmish.parent:
                # Create a top-level summary
                details = "\n\n".join(skirmish.full_details(
                    config=context.config))
                rname = context.reply(details, pm=False)
                if rname:
                    skirmish.summary_id = rname.name
                else:
                    # Couldn't reply, bail!
                    context.session.rollback()
                    context.reply("I'm sorry - an error occurred and "
                                  "I coudn't commit your skirmish.  Disregard "
                                  "the previous confirmation")
                    return
            else:
                # Update the top-level summary
                SkirmishCommand.update_summary(context, skirmish)

            context.session.commit()

        except db.NotPresentException as npe:
            standard = (("Your armies are currently in %s and thus cannot "
                         "participate in this battle.") %
                         npe.actually_am.markdown())
            marching = ""
            moving = context.player.is_moving()
            if moving:
                marching = ("\n\n(Your forces will arrive in %s at %s )" %
                            (moving.dest.markdown(), moving.arrival_str()))
            context.reply("%s%s" % (standard, marching))
        except db.TeamException as te:
            if te.friendly:
                context.reply("You cannot attack someone on your team")
            else:
                context.reply("You cannot aid the enemy!")
        except db.InProgressException:
            context.reply("You can only spearhead one offensive per battle "
                          "(though you may still assist others)")
        except db.InsufficientException as ie:
            if ie.requested <= 0:
                context.reply("You must use at least 1 troop!")
            else:
                context.reply(("You don't have %d troops to spare! "
                               "(you have committed %d total)") %
                              (ie.requested,
                               context.player.committed_loyalists))
        except db.TimingException as te:
            if te.side == 'late':
                context.reply(("Top-level attacks are disallowed in the last "
                               "%d seconds of a battle") % current.lockout)
            else:
                context.reply("The battle has not yet begun!")

    @failable
    def extract_subskirmish(self, context, battle):
        if not context.comment.author:
            return None

        # If we've already processed the parent, it wasn't us
        # (we bail out if we see ourself as author before marking as processed)
        pid = context.comment.parent_id
        found = context.session.query(Processed).filter_by(id36=pid).count()
        if found:
            return None

        # get_info is what you're looking for when you want get_comment
        parent = context.reddit.get_info(thing_id=pid)
        if not parent:
            logging.warn("Can't get parent %s" % pid)
            return None

        if not parent.author:  # Parent was deleted!
            return None

        if parent.author.name != context.config.username:
            # Record this in our processed list so we don't have to do this
            # again.
            context.session.add(Processed(id36=parent.name, battle=battle))
            context.session.commit()
            return None

        regex = re.compile(r"\(subskirmish (\d+)\)")
        result = regex.search(parent.body)
        if result:
            result = int(result.group(1))
            return result
        # The "\*" is the closing bold markup
        regex = re.compile(r"Skirmish #(\d+)\*")
        result = regex.search(parent.body)
        if result:
            result = int(result.group(1))
            return result

    def find_skirmish_named(self, name, context):
        parent = context.session.query(SkirmishAction).filter_by(
                    comment_id=name).first()
        return parent

    def find_skirmish_by_id(self, skid, context):
        parent = context.session.query(SkirmishAction).filter_by(
            id=skid).first()
        return parent

    @staticmethod
    def update_summary(context, skirmish):
        root = skirmish.get_root()
        if root.summary_id:
            tls = context.reddit.get_info(
                thing_id=root.summary_id)
            text = "\n\n".join(root.full_details(config=context.config))
            tls.edit(text)


class TimeCommand(Command):

    def execute(self, context):
        context.reply("The current time is: %s" % timestr())
