from pyparsing import *

from commands import (DefectCommand, InvadeCommand, MoveCommand,
                      SkirmishCommand, StatusCommand)

number = Word(nums)
string = QuotedString('"', '\\')
subreddit = Suppress("/r/") + Word(alphanums + "_-")
location = string | subreddit | Word(alphanums + "_-")

attack = Keyword("attack")
oppose = Keyword("oppose")
support = Keyword("support")
participate = attack | oppose | support
troop_types = Keyword("cavalry") | Keyword("infantry") | Keyword("ranged")
troop_aliases = Keyword("calvary") | Keyword("calvalry") | Keyword("range")
skirmishcmd = (participate("action") + Suppress("with") + number("amount") +
               Optional(troop_types | troop_aliases)("troop_type"))
skirmishcmd.setParseAction(SkirmishCommand)

invade = Keyword("invade")
invadecmd = invade + location("where")
invadecmd.setParseAction(InvadeCommand)

move = Keyword("lead")
movecmd = (move + Optional(number("amount") | Keyword("all")) +
           Suppress("to") + location("where"))
movecmd.setParseAction(MoveCommand)

defect = Keyword("defect")
team = Keyword("orangered") | Keyword("periwinkle")
defectcmd = (defect + Optional(Keyword("to") + team("team")))
defectcmd.setParseAction(DefectCommand)

statuscmd = Keyword("status")
statuscmd.setParseAction(StatusCommand)

root = statuscmd | movecmd | invadecmd | skirmishcmd | defectcmd


def parse(s):
    result = root.parseString(s)
    return result[0]
