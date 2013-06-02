from pyparsing import *

from commands import MoveCommand, StatusCommand

number = Word(nums)
string = QuotedString('"', '\\')
subreddit = Suppress("/r/") + Word(alphanums + "_-")

location = string | subreddit | Word(alphanums + "_-")

move = Keyword("lead")

movecmd = move + number("amount") + Suppress("to") + location("where")
movecmd.setParseAction(MoveCommand)

statuscmd = Keyword("status")
statuscmd.setParseAction(StatusCommand)

root = movecmd | statuscmd


def parse(s):
    result = root.parseString(s)
    return result[0]
