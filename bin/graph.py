#!/usr/bin/env python
import json
import sys

from graphviz import Graph


def main():
    source = sys.argv[1]
    with open(source, 'r') as infile:
        regions = json.load(infile)

    g = Graph('chroma', filename='chroma.graphview', format='png')
    for region in regions:
        name = region['name']
        style = {"style": "filled"}
        if "owner" in region:
            owner = region["owner"]
            if owner == 0:
                style["color"] = "orange"
            else:
                style["color"] = "blue"
                style["fontcolor"] = "white"

        g.node(name, **style)
        for conn in region['connections']:
            g.edge(name, conn)
    g.render()


if __name__ == '__main__':
    main()
