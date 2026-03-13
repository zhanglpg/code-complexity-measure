"""Functions with moderate complexity."""


def find_max(items):
    if not items:          # +1
        return None
    best = items[0]
    for item in items[1:]:  # +1
        if item > best:     # +2 (nesting)
            best = item
    return best


def process(data, flag):
    result = []
    for item in data:       # +1
        if flag:            # +2 (nesting)
            result.append(item * 2)
        else:
            if item > 0:    # +3 (nesting)
                result.append(item)
    return result
