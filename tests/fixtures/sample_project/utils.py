"""Utility module — imports from simple and moderate for coupling testing."""

from . import simple
from . import moderate


def transform(value):
    return simple.add(value, 1)


def process_all(items):
    return moderate.find_max(items)
