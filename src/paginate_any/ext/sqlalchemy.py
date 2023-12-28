from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sqlalchemy
from sqlalchemy import Column, ColumnElement, Select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from paginate_any.cursor_pagination import CursorPaginator, RowT
from paginate_any.datastruct import CurrentCursor, Ordering, PointerExpression
from paginate_any.exc import check_module_version


if TYPE_CHECKING:
    from typing import TypeAlias


__all__ = [
    'SQLAlchemyStoreT',
    'ColumnT',
    'SQLAlchemyCursorPaginator',
]


check_module_version('sqlalchemy', sqlalchemy.__version__, (2, 0), (3, 0))


SQLAlchemyStoreT: TypeAlias = tuple[AsyncSession, Select[Any]]
ColumnT: TypeAlias = Column[Any]


class SQLAlchemyCursorPaginator(CursorPaginator[ColumnT, SQLAlchemyStoreT, RowT]):
    async def _paginate_data(
        self,
        store: SQLAlchemyStoreT,
        cursor: CurrentCursor,
    ) -> list[RowT]:
        session, stmt = store
        if cursor.values:
            stmt = stmt.where(self._make_sql_cursor(cursor))

        order_by_fields = self._order_by_fields(cursor)
        stmt = stmt.order_by(None).order_by(*order_by_fields).limit(cursor.size + 2)
        result = await session.scalars(stmt)
        return list(result.all())

    def _make_sql_cursor(self, cursor: CurrentCursor) -> ColumnElement[bool]:
        expr, _ = cursor.query_conditions
        fields_tuple = tuple_(*(self._sort_fields[f] for f in cursor.sort_fields))
        values_tuple = tuple_(*(cursor.values or ()))
        if expr == PointerExpression.lt:
            q = fields_tuple <= values_tuple
        else:
            q = fields_tuple >= values_tuple
        return q

    def _order_by_fields(self, cursor: CurrentCursor) -> list[ColumnElement[Any]]:
        is_asc = cursor.query_conditions[1] == Ordering.ASC
        fields = []
        for f in cursor.sort_fields:
            col = self._sort_fields[f]
            fields.append(col if is_asc else col.desc())
        return fields
