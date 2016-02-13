try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

# Important distutils stuff:
#   This file from https://docs.python.org/2/distutils/
#   https://python-packaging-user-guide.readthedocs.org/en/latest/distributing.html

setup(
    name="chromabot",
    version="1.0",
    description= "Arbiter of the battle between orangered and periwinkle",
    author="Roger Ostrander",
    author_email="atiaxi@gmail.com",
    url="https://www.reddit.com/r/councilofkarma/wiki/chromabot",
    packages=['chromabot'],
    install_requires=[
        'praw>=3.3.0',
        'pyparsing>=2.1.0',
        'sqlalchemy>=1.0.11',
        'alembic>=0.8.4',
    ],
)
