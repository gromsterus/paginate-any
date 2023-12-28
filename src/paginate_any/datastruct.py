from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeAlias, TypeVar


__all__ = [
    'DictStrAny',
    'PointerExpression',
    'Ordering',
    'CursorValuesT',
    'CursorRawT',
    'CurrentCursor',
    'CursorPaginationPage',
]

DictStrAny: TypeAlias = dict[str, Any]


class PointerExpression(Enum):
    lt = 'lt'
    gt = 'gt'


class Ordering(Enum):
    ASC = 'ASC'
    DESC = 'DESC'

    @classmethod
    def reverse(cls, value: 'Ordering') -> 'Ordering':
        return cls.DESC if value == cls.ASC else cls.ASC

    @classmethod
    def get_direction(cls, val: str) -> 'Ordering':
        return cls.DESC if val.startswith('-') else cls.ASC


CursorValuesT: TypeAlias = tuple[Any, ...]
CursorRawT: TypeAlias = str | bytes | None


@dataclass(frozen=True, slots=True)
class CurrentCursor:
    before: CursorValuesT | None
    after: CursorValuesT | None
    size: int
    sort_fields: tuple[str, ...]
    sort_direction: Ordering

    @property
    def values(self) -> CursorValuesT | None:
        return self.after if self.after else self.before

    @property
    def reverse(self) -> bool:
        return bool(self.before)

    @property
    def query_conditions(self) -> tuple[PointerExpression, Ordering]:
        is_reversed = self.sort_direction == Ordering.DESC
        # example: DESC + before = gt | DESC + after = lt
        # example: ASC + before = lt | ASC + after = gt
        expression = (
            PointerExpression.lt if self.reverse != is_reversed else PointerExpression.gt
        )
        direction = (
            Ordering.reverse(self.sort_direction) if self.reverse else self.sort_direction
        )
        return expression, direction


_T = TypeVar('_T')


@dataclass(frozen=True, slots=True)
class CursorPaginationPage(Generic[_T]):
    cursor_params: CurrentCursor
    rows: list[_T]
    prev: str | None = None
    next: str | None = None
