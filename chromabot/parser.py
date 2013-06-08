from pyparsing import *

from commands import InvadeCommand, MoveCommand, StatusCommand

number = Word(nums)
string = QuotedString('"', '\\')
subreddit = Suppress("/r/") + Word(alphanums + "_-")
location = string | subreddit | Word(alphanums + "_-")

invade = Keyword("invade")
invadecmd = invade + location("where")
invadecmd.setParseAction(InvadeCommand)

move = Keyword("lead")
movecmd = move + number("amount") + Suppress("to") + location("where")
movecmd.setParseAction(MoveCommand)

statuscmd = Keyword("status")
statuscmd.setParseAction(StatusCommand)

root = movecmd | statuscmd | invadecmd


def parse(s):
    result = root.parseString(s)
    return result[0]
