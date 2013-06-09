import re


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


def num_to_team(number):
    return ('Orangered', 'Periwinkle')[number]
