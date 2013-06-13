from pyparsing import *

from commands import InvadeCommand, MoveCommand, SkirmishCommand, StatusCommand

number = Word(nums)
string = QuotedString('"', '\\')
subreddit = Suppress("/r/") + Word(alphanums + "_-")
location = string | subreddit | Word(alphanums + "_-")

attack = Keyword("attack")
support = Keyword("support")
participate = attack | support
skirmishcmd = participate("action") + Suppress("with") + number("amount")
skirmishcmd.setParseAction(SkirmishCommand)

invade = Keyword("invade")
invadecmd = invade + location("where")
invadecmd.setParseAction(InvadeCommand)

move = Keyword("lead")
movecmd = (move + Optional(number("amount") | Keyword("all")) +
           Suppress("to") + location("where"))
movecmd.setParseAction(MoveCommand)

statuscmd = Keyword("status")
statuscmd.setParseAction(StatusCommand)

root = statuscmd | movecmd | invadecmd | skirmishcmd


def parse(s):
    result = root.parseString(s)
    return result[0]
