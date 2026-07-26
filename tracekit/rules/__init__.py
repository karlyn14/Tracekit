"""
Rule registration happens here, once, at import time — before any
application threads are spawned. This is why the registry needs no
locking: it's built once during startup and treated as read-only for
the rest of the process's life.
"""

from tracekit.core.registry import default_registry
from tracekit.rules.keyerror_rules import (
    KeyErrorCaseMismatchRule,
    KeyErrorNestedSectionRule,
    KeyErrorTypoRule,
)

default_registry.register(KeyErrorTypoRule())
default_registry.register(KeyErrorCaseMismatchRule())
default_registry.register(KeyErrorNestedSectionRule())
