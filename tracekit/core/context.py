"""
ExceptionContext: a snapshot of everything a rule needs to inspect an
exception, built once at analysis time.

Design decision (defend this explicitly): this is a SNAPSHOT, not a
live wrapper around the frame object. We extract source text, local
variable names/types/reprs, and the AST of the failing line up front,
then deliberately drop the reference to the frame itself. Frames keep
their locals alive, and locals can keep arbitrarily large objects
alive (DataFrames, tensors, etc.) — holding onto frames after the
exception has been handled is a classic, avoidable memory leak.
"""

from __future__ import annotations

import ast
import linecache
import types
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExceptionContext:
    exc_type: type[BaseException]
    exc_value: BaseException
    filename: str
    lineno: int
    source_line: str
    ast_node: Optional[ast.AST]
    # Shallow snapshot only: name -> (type name, short repr). We never
    # keep the actual objects, so nothing here can retain user memory.
    local_vars: dict[str, tuple[str, str]] = field(default_factory=dict)
    # For locals that look dict-like or DataFrame-like, snapshot just
    # their key/column names as plain strings: name -> [key, key, ...].
    # This is what lets rules like KEY001 suggest "did you mean X"
    # without ever retaining a reference to the underlying object.
    available_keys: dict[str, list[str]] = field(default_factory=dict)
    # For dict-like locals (plain dicts ONLY — not DataFrame-like
    # objects, since "columns" has no dict-of-dicts structure), record
    # one level of nesting: outer_key -> [inner_key, inner_key, ...]
    # for every value that is itself a plain dict. Pooled across all
    # dict-like locals in scope, same convention as available_keys.
    # Deliberately capped at exactly one level — see KEY003's
    # docstring for why deeper recursive search is out of scope.
    nested_sections: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_exception(
        cls, exc_value: BaseException, tb: Optional[types.TracebackType]
    ) -> "ExceptionContext":
        # Walk to the innermost frame (the raise site) — see the
        # documented scope limitation: v1 diagnoses the raise site,
        # not upstream causal chains across the call stack.
        last_tb = tb
        while last_tb is not None and last_tb.tb_next is not None:
            last_tb = last_tb.tb_next

        frame = last_tb.tb_frame if last_tb is not None else None
        lineno = last_tb.tb_lineno if last_tb is not None else -1
        filename = frame.f_code.co_filename if frame else "<unknown>"

        source_line = ""
        if filename and lineno > 0:
            source_line = linecache.getline(filename, lineno).strip()

        ast_node = _safe_parse_line(source_line)

        local_vars: dict[str, tuple[str, str]] = {}
        available_keys: dict[str, list[str]] = {}
        nested_sections: dict[str, list[str]] = {}
        if frame is not None:
            for name, value in frame.f_locals.items():
                try:
                    local_vars[name] = (type(value).__name__, _safe_repr(value))
                except Exception:
                    local_vars[name] = ("<unknown>", "<unrepr-able>")

                keys = _safe_extract_keys(value)
                if keys is not None:
                    available_keys[name] = keys

                for section, inner_keys in _safe_extract_nested_sections(value).items():
                    nested_sections[section] = inner_keys

        # NOTE: we intentionally do not store `frame` or `tb` on self —
        # only the plain-string key names extracted above.
        return cls(
            exc_type=type(exc_value),
            exc_value=exc_value,
            filename=filename,
            lineno=lineno,
            source_line=source_line,
            ast_node=ast_node,
            local_vars=local_vars,
            available_keys=available_keys,
            nested_sections=nested_sections,
        )


def _safe_parse_line(line: str) -> Optional[ast.AST]:
    """Parse a single source line defensively; a failing/partial line
    (e.g. inside a multi-line call) may not parse standalone. Never
    raise — a rule with no AST node just falls back to string checks."""
    if not line:
        return None
    try:
        return ast.parse(line, mode="exec")
    except SyntaxError:
        return None


def _safe_extract_keys(value: Any) -> Optional[list[str]]:
    """
    Extract just the key/column names (as plain strings) from a
    dict-like or DataFrame-like object, without keeping any reference
    to the object or its values. Returns None if `value` doesn't look
    like either shape, or if anything about it can't be read safely.
    """
    try:
        if isinstance(value, dict):
            return [str(k) for k in value.keys()]
        columns = getattr(value, "columns", None)
        if columns is not None:
            return [str(c) for c in list(columns)]
    except Exception:
        return None
    return None


def _safe_extract_nested_sections(value: Any) -> dict[str, list[str]]:
    """
    For a plain dict whose values are themselves plain dicts, return
    {outer_key: [inner_key, ...]} — exactly one level deep, and ONLY
    for plain `dict` values (not DataFrame-like or other mapping
    types, which have no comparable nested-key structure). Never
    recurses past one level: this is a deliberate scope boundary for
    KEY003, not an oversight — see keyerror_rules.py.
    """
    sections: dict[str, list[str]] = {}
    if not isinstance(value, dict):
        return sections
    try:
        for key, inner in value.items():
            if isinstance(inner, dict):
                sections[str(key)] = [str(k) for k in inner.keys()]
    except Exception:
        return {}
    return sections


def _safe_repr(value: Any, max_len: int = 120) -> str:
    try:
        r = repr(value)
    except Exception:
        return "<unrepr-able>"
    return r if len(r) <= max_len else r[: max_len - 3] + "..."
