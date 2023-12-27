from asyncio import current_task
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from paginate_any.ext.sqlalchemy import SQLAlchemyCursorPaginator
from sqlalchemy import (
    DateTime,
    Select,
    String,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Mapped, mapped_column

from ._data_structures import (
    LogPaginatorFactory,
    utc_now,
)


if TYPE_CHECKING:
    hybrid_property = property
else:
    from sqlalchemy.ext.hybrid import hybrid_property


__all__ = [
    'engine',
    'scoped_session_cls',
    'create_db',
    'drop_db',
    'SQLAlchemyLogPaginatorFactory',
    'make_sqlalchemy_p_factory',
]


class Base(DeclarativeBase):
    pass


class SALog(Base):
    __tablename__ = 'logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    _created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        name='created',
    )

    @hybrid_property
    def created(self) -> datetime:
        return self._created.replace(tzinfo=timezone.utc)

    @created.setter
    def created(self, value: datetime) -> None:
        self._created = value.replace(tzinfo=timezone.utc)

    @created.expression
    def created(cls) -> InstrumentedAttribute[datetime]:
        return cast(InstrumentedAttribute[datetime], cls._created)


class SQLAlchemyLogPaginatorFactory(LogPaginatorFactory[SALog]):
    rows_store: tuple[AsyncSession, Select[tuple[SALog]]]
    paginator: type[SQLAlchemyCursorPaginator[SALog]]

    async def create_log(
        self,
        id: int,
        action: str = '',
        created: datetime | None = None,
    ) -> SALog:
        log = SALog(id=id, action=action, created=created or utc_now())
        self.rows_store[0].add(log)
        return log

    async def rm_log(self, row: SALog) -> None:
        await self.rows_store[0].delete(row)


engine = create_async_engine(
    'sqlite+aiosqlite:///:memory:',
    echo=False,
)
scoped_session_cls = async_scoped_session(
    async_sessionmaker(engine, expire_on_commit=False),
    scopefunc=current_task,
)


async def create_db(e: AsyncEngine):
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(e: AsyncEngine):
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def make_sqlalchemy_p_factory(s: AsyncSession) -> SQLAlchemyLogPaginatorFactory:
    return SQLAlchemyLogPaginatorFactory(
        rows_store=(s, select(SALog)),
        paginator=SQLAlchemyCursorPaginator,
        sort_fields={
            'id': SALog.id,
            'action': SALog.action,
            'created': SALog.created,
        },
    )
