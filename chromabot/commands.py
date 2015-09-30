import logging
import os
import re
import socket
import time
import traceback
from cStringIO import StringIO

import praw
from requests.exceptions import ConnectionError, HTTPError, Timeout

import db
from db import Battle, Buff, Region, Processed, SkirmishAction, User
from utils import now, num_to_team, team_to_num, timestr
from pathfinder import find_path


def failable(f):
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except (praw.errors.APIException, praw.errors.HTTPException):
            full = traceback.format_exc()
            logging.warning("Reddit API call failed! %s" % full)
            return None
        except ConnectionError:
            full = traceback.format_exc()
            logging.warning("Connection error: %s", full)
        except (Timeout, socket.timeout, socket.error):
            full = traceback.format_exc()
            logging.warning("Socket timeout! %s" % full)
            return None
        except HTTPError:
            full = traceback.format_exc()
            logging.warning("HTTP error %s" % full)
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
        verbose = self.config.bot.get("verbose_logging")
        was_comment = getattr(self.comment, 'was_comment', True)
        header = ""
        if was_comment and pm:
            header = ("(In response to [this comment](%s))" %
                      self.comment.permalink)
        else:  # It wasn't a comment, or pm = False
            if verbose:
                logging.info("Replying: %s" % reply)
            return self.comment.reply(reply)

        full_reply = "%s\n\n%s" % (header, reply)
        if verbose:
            logging.info("PMing: %s" % full_reply)
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


class CodewordCommand(Command):
    def __init__(self, tokens):
        self.remove = 'remove' in tokens
        self.all = 'all' in tokens
        self.status = 'status' in tokens
        if 'code' in tokens:
            self.code = tokens['code']
        else:
            self.code = None
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
            if self.code:
                troop_type = context.player.translate_codeword(self.code)
                if troop_type:
                    context.reply("The codeword `%s` translates to: `%s`" %
                                  (self.code, troop_type))
                else:
                    context.reply("`%s` does not appear to be "
                                  "a valid codeword" % self.code)
            else:
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
            context.player.defect(self.team, context.config)
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
        except db.DisabledException:
            context.reply("Defection has been disabled.")


class ExtractCommand(Command):
    def __init__(self, tokens):
        pass

    @failable
    def execute(self, context):
        try:
            context.player.extract()
            context.reply("You have successfully evacuated your team to %s" %
                          context.player.region.markdown())
        except db.InProgressException:
            context.reply("The zone is too hot for extraction!  You will have "
                          "to wait until the battle finishes.")


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
        dest = Region.get_region(self.where, context)
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
            except db.TimingException as te:
                context.reply(("%s is too fortified to be attacked.  "
                              "These fortifications will break down by %s") %
                              (dest.markdown(), timestr(te.expected)))

            if battle:
                context.reply("**Confirmed**  Battle will begin at %s" %
                              battle.begins_str())
                title = ("[Invasion] The %s armies march on %s!" %
                         (context.team_name(), dest.name))
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
        self.where = tokens["where"][:]
        self.names = [MoveCommand.canonicalize_name(d.destination)
                      for d in self.where]

    @staticmethod
    def canonicalize_name(name):
        if name:
            return name.lower()
        return name

    def execute(self, context):
        dests = MoveCommand.expand_path(self.names, context)
        if dests and None not in dests:
            if self.amount == -1:  # -1 means 'everyone'
                self.amount = context.player.loyalists

            try:
                speed = context.config["game"]["speed"]
                #hundred_followers = self.amount / 100
                time_taken = speed  # * hundred_followers

                orders = context.player.move(
                    self.amount, dests, time_taken,
                    sector=self.where[-1].destination_sector,
                    conf=context.config)
            except db.InsufficientException as ie:
                context.reply(
                    "You cannot move %d of your people - you only have %d" %
                    (ie.requested, ie.available))
                return
            except db.NonAdjacentException as nae:
                text = ("The region %s is not adjacent to %s" %
                    (nae.src.markdown(), nae.dest.markdown()))
                if context.player.region == nae.dest:
                    text = ("How can you go to %s when "
                            "you are *already here*?") % nae.dest.markdown()
                context.reply(text)

                return
            except db.NoSuchSectorException as nsse:
                context.reply(str(nsse))
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
            except db.TeamException as te:
                context.reply(("%s is not friendly territory - invade first "
                               "if you want to go there") % te.what.markdown())
                return
            context.player.defectable = False
            if orders:
                itinerary = [mo.markdown() for mo in orders]
                context.reply("**Confirmed**:  Your troops are moving:\n\n" +
                               ("\n\n".join(itinerary)))
            else:
                context.reply((
                    "**Confirmed**: You have lead %d of your people to %s."
                    ) % (self.amount, dests[-1].markdown()))
            context.session.commit()

    @classmethod
    def expand_path(cls, regions, context):
        if "*" not in regions:
            return [Region.get_region(where, context) for where in regions]
        if regions[-1] == '*':
            context.reply("You can't end a movement command with a "
                          "pathfinding instruction; I have no idea where you "
                          "want to end up!")
            return
        result = []
        curr = context.player.region
        for index, region_name in enumerate(regions):
            if region_name == '*':
                if not curr:
                    continue  # Don't bother if we don't know prev location
                if regions[index + 1] == '*':
                    continue  # Ignore consecutive pathfinding instructions
                dest = Region.get_region(regions[index + 1], context)
                if not dest:
                    return None

                # See if we allow neutral traversal
                conf = context.config
                traverse_neutrals = False
                if conf:
                    traverse_neutrals = conf["game"].get("traversable_neutrals",
                                                         False)
                path = find_path(curr, dest, context.player.team,
                                 traverse_neutrals=traverse_neutrals)
                if path:
                    path = path[1:-1]  # We already have the first and the last
                    if not path:
                        continue  # They were already adjacent!
                    result.extend(path)
                else:
                    context.reply("I couldn't find a friendly-territory path "
                                  "between %s and %s "
                                  % (curr.name, dest.name))
                    return None
                curr = dest
            else:
                dest = Region.get_region(region_name, context)
                if not dest:
                    return None
                result.append(dest)
                curr = dest
        return result

    def __repr__(self):
        return "<MoveCommand(amount='%s', where='%s')>" % (
            self.amount, self.where)


class StatusCommand(Command):

    @classmethod
    def lands_status_for(cls, session, config):
        regions = session.query(Region).all()
        fmt = "* **%s**:  %s%s"
        result = []
        for region in regions:
            dispute = ""
            if region.battle:
                dispute = " ( %s )" % region.battle.markdown()
            if region.buffs:
                bufflist = [buff.markdown() for buff in region.buffs]
                dispute += " ( %s )" % ",".join(bufflist)
            result.append(fmt % (region.markdown(),
                                 num_to_team(region.owner, config),
                                 dispute))
        result.sort()
        lands = "\n".join(result)
        return "State of the Lands:\n\n" + lands

    def execute(self, context):
        status = self.status_for(context)
        context.reply(status)

    def lands_status(self, context):
        return StatusCommand.lands_status_for(context.session, context.config)

    def status_for(self, context):
        found = context.player

        moving = context.player.is_moving()
        sector = 0
        if found.sector:
            sector = found.sector
        encamp = ("You are currently encamped in sector %d of  %s" %
                  (sector, found.region.markdown()))
        forces = ""
        if moving:
            itinerary = [mo.markdown() for mo in moving]
            forces = ("\n\nYour troops are currently on the march:\n\n" +
                "\n\n".join(itinerary))

        commit_str = ""
        if found.committed_loyalists:
            commit_str = (", %d of which are committed to battle" %
                          found.committed_loyalists)
        result = ("You are a %s in the %s army.\n\n"
                  "Your forces number %d loyalists%s.\n\n"
                  "%s%s")
        personal = result % (found.rank, context.team_name(),
                             found.loyalists, commit_str, encamp, forces)
        return personal


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

    def first_strike(self, context, skirm):
        """Returns true if this skirmish is eligible for first strike"""
        fftb = context.config['game'].get('fftb_time', 0)
        if fftb:
            pre = (context.session.query(SkirmishAction).
                   filter_by(battle=skirm.battle,
                             participant=skirm.participant)).count()
            cutoff = skirm.battle.begins + fftb
            if now() <= cutoff and pre <= 1:
                return True

    def execute(self, context):
        # getattr wackiness because real comments not gotten from inbox don't
        # have "was_comment" set on them
        if not getattr(context.comment, 'was_comment', True):
            if context.config.game.get("battle_pm", False):
                # Must be targeting something
                if not self.target:
                    context.reply("PMed skirmish commands must target an "
                                  "ongoing skirmish!")
                    return
            else:
                # PMing skirmish commands is disabled
                context.reply("You must enter your skirmish commands in the "
                              "appropriate battle post")
                return
            current = None
        else:
            post_id = context.comment.link_id  # Actually a 'name'
            ongoing = context.session.query(Battle).filter_by(
                submission_id=post_id)
            current = ongoing.first()
            if not current:
                context.reply("There's no battle happening here!")
                return

        try:
            enforce = context.config["bot"].get("enforce_noob_rule", True)
            if not self.target and post_id == context.comment.parent_id:
                skirmish = current.create_skirmish(context.player, self.amount,
                                                   troop_type=self.troop_type,
                                                   enforce_noob_rule=enforce,
                                                   conf=context.config)
            else:
                if self.target:
                    parent = self.find_skirmish_by_id(self.target, context)
                    if parent and current and parent.battle != current:
                        context.reply("That skirmish belongs to "
                                      "another battle!")
                        return
                    if not parent:
                        context.reply("That does not appear to be a valid "
                                      "skirmish!")
                        return
                    if not current:
                        current = parent.battle  # For PMed skirmish commands
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
                                        troop_type=self.troop_type,
                                        enforce_noob_rule=enforce)
            total = context.player.committed_loyalists

            if self.first_strike(context, skirmish):
                skirmish.buff_with(Buff.first_strike())

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
                            (moving[0].dest.markdown(), moving[0].arrival_str()))
            context.reply("%s%s" % (standard, marching))
        except db.TeamException as te:
            if te.friendly:
                context.reply("You cannot attack someone on your team")
            else:
                context.reply("You cannot aid the enemy!")
        except db.InProgressException as ipe:
            if isinstance(ipe.other, Battle):
                context.reply("You can only spearhead one offensive per "
                              "battle (though you may still assist others)")
            elif isinstance(ipe.other, SkirmishAction):
                context.reply("You may only respond to a specific "
                              "sub-skirmish once (though you may still "
                              "fight elsewhere)")
            elif hasattr(ipe.other, 'arrival_str'):
                mkdown = ipe.other.dest.markdown()
                context.reply("Your troops are moving to %s - they are in "
                              "no condition to fight!" % mkdown)

        except db.InsufficientException as ie:
            if ie.requested <= 0:
                context.reply("You must use at least 1 troop!")
            else:
                context.reply(("You don't have %d troops to spare! "
                               "(you have committed %d total)") %
                              (ie.requested,
                               context.player.committed_loyalists))
        except db.TooManyException as tme:
            context.reply("You may commit at most %d troops to that skirmish" %
                          tme.max)
        except db.TimingException as te:
            if te.side == 'late' and te.expected is None:
                context.reply(("Top-level attacks are disallowed in the last "
                               "%d seconds of a battle") % current.lockout)
            elif te.side == 'late':
                context.reply("That skirmish has ended!")
            else:
                # If the battle's begun, it's the user that is too young
                if current.has_started():
                    context.reply("You cannot participate in a battle "
                                  "created before you signed up.")
                else:
                    context.reply("The battle has not yet begun!")
        except db.WrongSectorException as wse:
            context.reply(str(wse))
        except db.NoSuchSectorException:
            context.reply("You must first move to a sector")

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

        if parent.author.name.lower() != context.config.username.lower():
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
    @failable
    def update_summary(context, skirmish):
        root = skirmish.get_root()
        if root.summary_id:
            summary_ids = root.summary_id.split(",")
            initial_id = summary_ids[0]
            full_details = root.full_details(config=context.config)
            summaries = []
            partial_summary = StringIO()
            for detail in full_details:
                partial_summary.write(detail + "\n\n")
                partial_summary.seek(0, os.SEEK_END)
                if partial_summary.tell() > 9800:
                    summaries.append(partial_summary)
                    partial_summary = StringIO()
            summaries.append(partial_summary)

            tries = 0
            while len(summaries) > len(summary_ids):
                initial_post = context.reddit.get_info(thing_id=initial_id)
                curr = summaries[len(summary_ids)]
                summary = initial_post.reply(curr.getvalue())
                if summary:
                    summary_ids.append(summary.name)
                    root.summary_id = ",".join(summary_ids)
                else:
                    tries = tries + 1
                    if tries > 5:
                        # Something seriously wrong, bail!
                        context.session.rollback()
                        context.reply("I'm sorry - an error occurred and "
                            "I coudn't commit your skirmish.  Disregard "
                            "the previous confirmation")
                        return

            for index, partial in enumerate(summaries):
                this_id = summary_ids[index]
                if index < len(summaries) - 1:
                    next_id = summary_ids[index + 1]
                    tls = context.reddit.get_info(thing_id=next_id)
                    partial.write("[Next](%s)" % tls.permalink)
                tls = context.reddit.get_info(thing_id=this_id)
                tls.edit(partial.getvalue())
            context.session.commit()


class TimeCommand(Command):

    def execute(self, context):
        context.reply("The current time is: %s" % timestr())
