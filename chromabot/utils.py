import os
import re
import time
from itertools import izip, tee
from urllib import quote_plus


def base36decode(number):
    return int(number, 36)


def extract_command(text):
    text = text.strip()
    regex = re.compile(r"(?:\n|^)>(.*)")
    result = regex.findall(text)
    return result


def forcelist(item):
    """Forces casting of a non-string iterable to a list or generates a
    single element list (for anything else)"""
    if hasattr(item, '__iter__') and not isinstance(item, basestring):
        return list(item)
    else:
        return [item, ]


def name_to_id(name):
    """Convert a reddit name of the form t3_xx to xx"""
    results = name.split("_")
    if(len(results) != 2):
        raise ValueError("Expected %s to be splittable!" % name)
    return results[1]


def now():
    return time.mktime(time.localtime())


def num_to_team(number, config=None):
    if config is None:
        config = {
            "game": {
                "sides": ["Orangered", "Periwinkle"]
            }
        }
    if number is not None:
        return config['game']['sides'][number]
    return "Neutral"


# Courtesy python docs
#   http://docs.python.org/2/library/itertools.html
def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


def team_to_num(team):
    teams = {"orangered": 0, "periwinkle": 1}
    return teams.get(team.lower(), None)


def timestr(secs=None):
    if secs is None:
        secs = time.mktime(time.localtime())

    timeresult = time.gmtime(secs)
    timestresult = time.strftime("%Y-%m-%d %I:%M:%S %p GMT", timeresult)
    url = ("http://www.wolframalpha.com/input/?i=%s+in+local+time" %
           quote_plus(timestresult))
    return "[%s](%s)" % (timestresult, url)


def version(config):
    result = "Unknown"
    rdir = config["bot"].get("report_dir")
    if rdir:
        fullpath = os.path.join(rdir, "VERSION")
        if os.path.exists(fullpath):
            with file(fullpath, 'r') as f:
                result = f.readline()
    return result
