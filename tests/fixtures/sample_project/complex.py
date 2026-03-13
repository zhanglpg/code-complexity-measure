"""A highly complex function for hotspot testing."""

from . import utils


def handle_request(request, config, db):
    if not request:                  # +1
        return None
    if not config:                   # +1
        return None

    result = []
    for item in request.items:       # +1
        if item.type == "a":         # +2 (nesting)
            for sub in item.children:  # +3 (nesting)
                if sub.valid:          # +4 (nesting)
                    try:
                        val = utils.transform(sub)
                        if val > 0:        # +5 (nesting=4, except increments)
                            result.append(val)
                    except Exception:      # +4 (nesting)
                        if config.strict:  # +5 (nesting)
                            raise
        elif item.type == "b":       # +1 (elif, flat)
            while item.has_next():   # +3 (nesting)
                item = item.next()
                if item.skip:        # +4 (nesting)
                    continue         # +1
                result.append(item)

    return result
