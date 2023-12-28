import abc
import binascii
import logging
from itertools import islice
from typing import Any, Generic, Protocol, TypeAlias, TypeVar, final, runtime_checkable

import msgspec
from pybase64 import urlsafe_b64decode, urlsafe_b64encode

from .datastruct import (
    CurrentCursor,
    CursorPaginationPage,
    CursorRawT,
    CursorValuesT,
    Ordering,
    PointerExpression,
)
from .exc import (
    ConfigurationErr,
    CursorValueErr,
    MultipleCursorsErr,
    PaginationErr,
    SortParamErr,
)


__all__ = [
    'SortFieldsRawT',
    'SortFieldsT',
    'FieldT',
    'RowT',
    'RowsStoreT',
    'CursorPaginator',
    'InMemoryCursorPaginator',
]


logger = logging.getLogger(__name__)
SortFieldsRawT: TypeAlias = str | None
SortFieldsT: TypeAlias = tuple[str, ...]


_KT_contra = TypeVar('_KT_contra', contravariant=True)
_VT_co = TypeVar('_VT_co', covariant=True)


@runtime_checkable
class _SupportsGetItem(Protocol[_KT_contra, _VT_co]):
    def __contains__(self, __x: Any) -> bool:  # pragma: no cover
        ...

    def __getitem__(self, __key: _KT_contra) -> _VT_co:  # pragma: no cover
        ...


FieldT = TypeVar('FieldT')
RowT = TypeVar('RowT', bound=_SupportsGetItem[str, Any] | object)
RowsStoreT = TypeVar('RowsStoreT')


_cursor_encode = msgspec.msgpack.Encoder().encode
_cursor_decode = msgspec.msgpack.Decoder(type=CursorValuesT).decode
_cursor_decode_err = msgspec.DecodeError


class CursorPaginator(Generic[FieldT, RowsStoreT, RowT], metaclass=abc.ABCMeta):
    __slots__ = (
        '_unq_field',
        '_sort_fields',
        'default_sort',
        'default_size',
        'max_size',
    )

    default_sort: SortFieldsRawT
    max_size: int | None
    default_size: int

    def __init__(  # noqa: PLR0913
        self,
        unq_field: str,
        sort_fields: dict[str, FieldT],
        default_size: int = 20,
        max_size: int | None = 100,
        default_sort: SortFieldsRawT = None,
    ) -> None:
        self._unq_field = unq_field
        self._sort_fields = sort_fields
        self.default_sort = default_sort

        if unq_field not in sort_fields:
            msg = '"unq_field" must be in "sort_fields"'
            raise ConfigurationErr(msg)

        if max_size is not None and max_size <= 0:
            msg = '"max_size" must be > 0'
            raise ConfigurationErr(msg)
        self.max_size = max_size

        if default_size <= 0:
            msg = '"default_size" must be > 0'
            raise ConfigurationErr(msg)
        if max_size is not None and default_size > max_size:
            msg = '"default_size" must be <= "max_size"'
            raise ConfigurationErr(msg)
        self.default_size = default_size

    async def paginate(  # noqa: PLR0913
        self,
        store: RowsStoreT,
        sort_fields: SortFieldsRawT = None,
        before: CursorRawT = None,
        after: CursorRawT = None,
        size: int | None = None,
    ) -> CursorPaginationPage[RowT]:
        cursor = self._make_cursor(before, after, sort_fields, size)
        rows, has_prev, has_next = await self._get_rows(store, cursor)
        return CursorPaginationPage(
            cursor_params=cursor,
            rows=rows,
            prev=self._get_cursor_value(rows[0], cursor) if rows and has_prev else None,
            next=self._get_cursor_value(rows[-1], cursor) if rows and has_next else None,
        )

    def _get_cursor_value(self, row: RowT, cursor: CurrentCursor) -> str:
        cursor_values: list[Any] = []
        for f in cursor.sort_fields:
            if (value := self._get_field_val(row, f)) is None:
                msg = f'Cursor value must not be None (field: "{f}")'
                logger.error(msg)
                raise PaginationErr(msg)
            cursor_values.append(value)
        return self._encode_cursor(cursor_values)

    @staticmethod
    def _encode_cursor(cursor_values: list[Any]) -> str:
        return urlsafe_b64encode(_cursor_encode(cursor_values)).decode('utf-8')

    def _get_field_val(self, row: RowT, field: str) -> Any:
        err: Exception | None
        try:
            return getattr(row, field)
        except AttributeError as exc:
            err = exc

        if isinstance(row, _SupportsGetItem):
            try:
                return row[field]
            except LookupError as exc:
                err = exc

        msg = "Can't get cursor value from row"
        logger.exception(msg, exc_info=err)
        raise PaginationErr(msg) from err

    def _make_cursor(
        self,
        before_raw: CursorRawT,
        after_raw: CursorRawT,
        sort_fields_raw: SortFieldsRawT,
        size: int | None = None,
    ) -> CurrentCursor:
        sort_fields, direction = self._get_sort_fields(
            sort_fields_raw or self.default_sort,
        )
        after, before = self._get_after_and_before(before_raw, after_raw, sort_fields)

        size = self.default_size if size is None else size
        if size <= 0:
            size = 1
        elif self.max_size and size > self.max_size:
            size = self.max_size

        return CurrentCursor(
            after=after,
            before=before,
            size=size,
            sort_fields=sort_fields,
            sort_direction=direction,
        )

    def _get_sort_fields(self, fields: SortFieldsRawT) -> tuple[SortFieldsT, Ordering]:
        if fields:
            direction = Ordering.get_direction(fields)
            fields_ = fields.removeprefix('-')
            sort_fields = fields_.split(',')
        else:
            direction, sort_fields = Ordering.ASC, []

        unq_field = self._unq_field
        if bad_fields := (set(sort_fields) - set(self._sort_fields)):
            msg = f'Remove "{bad_fields}" fields'
            raise SortParamErr(detail=msg)
        if unq_field in sort_fields and sort_fields[-1] != unq_field:
            msg = f'Move "{unq_field}" field to the end'
            raise SortParamErr(detail=msg)
        if unq_field not in sort_fields:
            sort_fields.append(unq_field)

        return tuple(sort_fields), direction

    def _get_after_and_before(
        self,
        before_raw: CursorRawT,
        after_raw: CursorRawT,
        sort_fields: SortFieldsT,
    ) -> tuple[CursorValuesT | None, CursorValuesT | None]:
        if after_raw is not None and before_raw is not None:
            raise MultipleCursorsErr()

        if after_raw:
            cursor_values = self._decode_cursor(after_raw)
        elif before_raw:
            cursor_values = self._decode_cursor(before_raw)
        else:
            return None, None

        if len(cursor_values) != len(sort_fields):
            raise CursorValueErr()
        return (cursor_values, None) if after_raw else (None, cursor_values)

    @staticmethod
    def _decode_cursor(s: str | bytes) -> CursorValuesT:
        try:
            return _cursor_decode(urlsafe_b64decode(s))
        except binascii.Error as exc:
            raise CursorValueErr(detail='Invalid base64 value') from exc
        except _cursor_decode_err as exc:
            msg = 'Invalid cursor value'
            raise CursorValueErr(detail=msg) from exc

    async def _get_rows(
        self,
        store: RowsStoreT,
        cursor: CurrentCursor,
    ) -> tuple[list[RowT], bool, bool]:
        rows = await self._paginate_data(store, cursor)

        has_prev, has_next = False, False
        if not rows:
            return rows, has_prev, has_next

        cursor_values = cursor.values
        if (
            cursor_values
            and self._get_field_val(rows[0], self._unq_field) == cursor_values[-1]
        ):
            rows.pop(0)
            if cursor.reverse:
                has_next = True
            else:
                has_prev = True

        if len(rows) > cursor.size:
            for _ in range(len(rows) - cursor.size):
                rows.pop()

            if cursor.reverse:
                has_prev = True
            else:
                has_next = True

        if cursor.reverse:
            # If we have a reverse data, then the query ordering was in reverse,
            # so we need to reverse the items again before returning them to the user
            rows.reverse()

        return rows, has_prev, has_next

    @abc.abstractmethod
    async def _paginate_data(
        self,
        store: RowsStoreT,
        cursor: CurrentCursor,
    ) -> list[RowT]:
        ...


_T = TypeVar('_T')


@final
class InMemoryCursorPaginator(CursorPaginator[str, list[_T], _T]):
    """Example of using a cursor with a list of anything in memory."""

    async def _paginate_data(
        self,
        store: list[_T],
        cursor: CurrentCursor,
    ) -> list[_T]:
        expr, sort_direction = cursor.query_conditions

        def get_list_cursor(row: Any) -> tuple[Any, ...]:
            return tuple(self._get_field_val(row, f) for f in cursor.sort_fields)

        rows_ = sorted(
            store,
            key=get_list_cursor,
            reverse=sort_direction == Ordering.DESC,
        )
        if cursor_values := cursor.values:
            cursor_tuple = tuple(cursor_values)

            def expr_func(row: Any) -> bool:
                row_cursor_value = get_list_cursor(row)
                if expr == PointerExpression.lt:
                    return row_cursor_value <= cursor_tuple
                return row_cursor_value >= cursor_tuple

            rows_ = list(filter(expr_func, rows_))

        rows = list(islice(rows_, cursor.size + 2))
        return rows
