

def find_path(src, dest, team=None):
    queue = []
    examined = set((src,))
    curr = (src,)
    try:
        while curr[-1] != dest:
            region = curr[-1]
            children = []
            for border in region.borders:
                if team is None or border.enterable_by(team):
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
