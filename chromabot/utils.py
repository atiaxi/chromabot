import re
import time


def base36decode(number):
    return int(number, 36)


def extract_command(text):
    text = text.strip()
    regex = re.compile(r"(?:\n|^)&gt;(.*)")
    result = regex.search(text)
    if result:
        cmd = result.group(1).strip()
        return cmd


def name_to_id(name):
    """Convert a reddit name of the form t3_xx to xx"""
    results = name.split("_")
    if(len(results) != 2):
        raise ValueError("Expected %s to be splittable!" % name)
    return results[1]


def now():
    return time.mktime(time.localtime())


def num_to_team(number):
    if number is not None:
        return ('Orangered', 'Periwinkle')[number]
    return "Neutral"


def team_to_num(team):
    teams = {"orangered": 0, "periwinkle": 1}
    return teams.get(team.lower(), None)
