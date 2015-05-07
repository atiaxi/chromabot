

def find_path(src, dest, team=None, traverse_neutrals=False):
    queue = []
    examined = set((src,))
    curr = (src,)
    try:
        while curr[-1] != dest:
            region = curr[-1]
            children = []
            for border in region.borders:
                enterable = border.enterable_by(
                    team, traverse_neutrals=traverse_neutrals)
                if team is None or enterable:
                    if border in examined:
                        continue
                    examined.add(border)
                    child = curr + (border,)
                    children.append(child)
            queue.extend(children)
            curr = queue.pop(0)
        else:
            return curr
    except IndexError:
        return None
