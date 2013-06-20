import json
import logging
import os.path

import praw


class Config(object):

    def __init__(self, conffile=None):
        # Try to locate our configuration directory

        proposals = [conffile, os.environ.get("CHROMABOT_CONFIG"),
                    "../config/config.json", "./config/config.json",
                    "/etc/chromabot/config.json"]

        if not self.check_exist(proposals):
            logging.error("Could not locate config file!")
            raise SystemExit

        self.refresh()

    def __getitem__(self, key):
        return self.data[key]

    def check_exist(self, proposed_paths):
        for fullpath in proposed_paths:
            if fullpath and os.path.exists(fullpath):
                self.conffile = fullpath
                return True
        return False

    def praw(self):
        """Return a praw.Reddit object configured according to this config"""
        ua = self.data["bot"]["useragent"]
        site = self.data["bot"].get('site')
        return praw.Reddit(user_agent=ua, site_name=site)

    def refresh(self):
        with open(self.conffile) as data_file:
            self.data = json.load(data_file)

    # Useful properties follow
    @property
    def dbstring(self):
        return self.data["db"]["connection"]

    @property
    def headquarters(self):
        return self.data["bot"]["hq_sub"]

    @property
    def password(self):
        return self.data["bot"]["password"]

    @property
    def username(self):
        return self.data["bot"]["username"]
