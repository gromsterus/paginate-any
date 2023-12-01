import abc
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from paginate_any.cursor_pagination import CursorPaginator, InMemoryCursorPaginator
from paginate_any.datastruct import CursorPaginationPage


__all__ = [
    'LogPaginatorFactory',
    'InMemoryLogPaginatorFactory',
    'utc_now',
]


# TODO: revert after fix https://github.com/python/mypy/issues/7724
# class LogT(Protocol):
#     id: int  # noqa: ERA001
#     action: str  # noqa: ERA001
#     created: datetime  # noqa: ERA001

LogT = TypeVar('LogT')


@dataclass
class LogPaginatorFactory(Generic[LogT], metaclass=abc.ABCMeta):
    rows_store: Any
    paginator: type[CursorPaginator[Any, Any, LogT]]
    sort_fields: dict[str, Any]

    @abc.abstractmethod
    async def create_log(
        self,
        id: int,
        action: str = '',
        created: datetime | None = None,
    ) -> LogT:
        pass

    @abc.abstractmethod
    async def rm_log(self, row: LogT) -> None:
        pass

    @property
    def p(self) -> CursorPaginator[Any, Any, LogT]:
        return self.paginator(
            unq_field='id',
            sort_fields=self.sort_fields,
            default_size=2,
            max_size=3,
        )

    async def paginate(self, **kwargs) -> CursorPaginationPage[LogT]:
        return await self.p.paginate(self.rows_store, **kwargs)


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class Log:
    id: int
    action: str
    created: datetime


class InMemoryLogPaginatorFactory(LogPaginatorFactory[Log]):
    rows_store: list[Log]
    paginator: type[InMemoryCursorPaginator[Log]]

    async def create_log(
        self,
        id: int,
        action: str = '',
        created: datetime | None = None,
    ) -> Log:
        log = Log(id, action, created or utc_now())
        self.rows_store.append(log)
        return log

    async def rm_log(self, row: Log) -> None:
        self.rows_store.remove(row)
