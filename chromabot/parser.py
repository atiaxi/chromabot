from pyparsing import *

from commands import (CodewordCommand,
                      DefectCommand,
                      ExtractCommand,
                      InvadeCommand,
                      MoveCommand,
                      PromoteCommand,
                      SkirmishCommand,
                      StatusCommand,
                      TimeCommand)

number = Word(nums)
string = QuotedString('"', '\\')
subreddit = Suppress("/r/") + Word(alphanums + "_-")
location = string | subreddit | Word(alphanums + "_-")
eolstring = Word(printables + " ")

attack = Keyword("attack")
oppose = Keyword("oppose")
support = Keyword("support")
participate = attack | oppose | support
troop_types = Keyword("cavalry") | Keyword("infantry") | Keyword("ranged")
troop_aliases = Keyword("calvary") | Keyword("calvalry") | Keyword("range")
alltroops = troop_types | troop_aliases
target = Suppress("#") + number("target")
skirmishcmd = (participate("action") + Optional(target) +
               Suppress("with") + number("amount") +
               Optional(eolstring)("troop_type"))
skirmishcmd.setParseAction(SkirmishCommand)

invade = Keyword("invade")
invadecmd = invade + location("where")
invadecmd.setParseAction(InvadeCommand)

move = Keyword("lead")
movecmd = (move + Optional(number("amount") | Keyword("all")) +
           Suppress("to") + delimitedList(location | Keyword("*"))("where"))
movecmd.setParseAction(MoveCommand)

extractcmd = Keyword("extract")
extractcmd.setParseAction(ExtractCommand)

defect = Keyword("defect")
team = Keyword("orangered") | Keyword("periwinkle")
defectcmd = (defect + Optional(Keyword("to") + team("team")))
defectcmd.setParseAction(DefectCommand)

promote = (Keyword("promote") | Keyword("demote"))
promotecmd = promote("direction") + Word(alphanums + "_-")("who")
promotecmd.setParseAction(PromoteCommand)

timecmd = Keyword("time")
timecmd.setParseAction(TimeCommand)


removecode = Keyword("remove")('remove') + (Keyword("all")('all')
                                            | string("code"))
assigncode = string("code") + Keyword("is") + alltroops("troop_type")
statuscode = Keyword("status")('status')
codewordcmd = Keyword("codeword") + (removecode | statuscode | assigncode)
codewordcmd.setParseAction(CodewordCommand)

statuscmd = Keyword("status")
statuscmd.setParseAction(StatusCommand)

root = (statuscmd | movecmd | invadecmd | skirmishcmd | defectcmd |
        promotecmd | timecmd | codewordcmd | extractcmd)


def parse(s):
    result = root.parseString(s)
    return result[0]
