import math
import re


__all__ = [
    'PaginationErr',
    'ConfigurationErr',
    'CursorParamsErr',
    'SortParamErr',
    'CursorValueErr',
    'MultipleCursorsErr',
    'check_module_version',
]


class PaginationErr(Exception):
    ...


class ConfigurationErr(PaginationErr):
    ...


class CursorParamsErr(PaginationErr):
    title: str = 'Cursor params error'
    detail: str | None = None

    def __init__(
        self,
        title: str | None = None,
        detail: str | None = None,
    ) -> None:
        if title is not None:
            self.title = title
        if detail is not None:
            self.detail = detail


class SortParamErr(CursorParamsErr):
    title: str = 'Invalid sort param'


class CursorValueErr(CursorParamsErr):
    title: str = 'Cursor value error'


class MultipleCursorsErr(CursorParamsErr):
    title: str = 'Multiple cursors error'
    detail: str = 'Only one cursor can be used in a query'


def check_module_version(
    name: str,
    v: str,
    min_v: tuple[int, ...],
    max_v: tuple[int, ...] | None = None,
) -> None:
    """Check minimum (inclusive) and maximum (exclusive) module version."""
    if min_v <= _v_to_tuple(v) < (max_v or (math.inf,)):
        return

    err = f'Module supports {name}>={".".join(map(str, min_v))}'
    if max_v:
        err += f',<{".".join(map(str, max_v))}'
    raise RuntimeError(err)


def _v_to_tuple(v: str) -> tuple[int, int, int]:
    pattern = r'(\d+)[a-z]*\d*\.(\d+)[a-z]*\d*\.?(\d+)?[a-z]*\d*'

    match = re.match(pattern, v)
    if match is None:
        msg = (
            'Invalid version fmt,\n'
            'see also https://packaging.python.org/en/latest/specifications/version-specifiers/#version-specifiers'
        )
        raise ValueError(msg)

    major, minor, patch = match.groups()
    return int(major), int(minor), 0 if patch is None else int(patch)
