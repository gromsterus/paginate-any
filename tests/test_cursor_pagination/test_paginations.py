import base64
from collections.abc import AsyncGenerator
from functools import partial
from typing import TYPE_CHECKING, Any, cast

import pytest
import pytest_asyncio

from paginate_any.cursor_pagination import InMemoryCursorPaginator
from paginate_any.exc import (
    ConfigurationErr,
    CursorParamsErr,
    CursorValueErr,
    MultipleCursorsErr,
    PaginationErr,
)

from ._data_structures import (
    InMemoryLogPaginatorFactory,
    LogPaginatorFactory,
)


if TYPE_CHECKING:
    from ._ext_sqlalchemy import SQLAlchemyLogPaginatorFactory


@pytest.fixture()
def in_memory_p_factory() -> InMemoryLogPaginatorFactory:
    return InMemoryLogPaginatorFactory(
        rows_store=[],
        paginator=InMemoryCursorPaginator,
        sort_fields={k: k for k in ('id', 'action', 'created')},
    )


@pytest_asyncio.fixture()
async def sqlalchemy_p_factory() -> AsyncGenerator['SQLAlchemyLogPaginatorFactory', None]:
    try:
        import sqlalchemy  # noqa: F401
    except ImportError as e:
        pytest.skip(str(e))

    from ._ext_sqlalchemy import (
        create_db,
        drop_db,
        engine,
        make_sqlalchemy_p_factory,
        scoped_session_cls,
    )

    await create_db(engine)
    session = scoped_session_cls()
    await session.begin()

    yield make_sqlalchemy_p_factory(session)

    await session.rollback()
    await drop_db(engine)
    await engine.dispose()


class PFactoryReq(pytest.FixtureRequest):
    param: str


@pytest.fixture(
    params=[
        pytest.param(
            'sqlalchemy',
            marks=[pytest.mark.integration, pytest.mark.sqlalchemy],
        ),
        'in_memory',
    ],
)
def p_factory(request: PFactoryReq) -> LogPaginatorFactory[Any]:
    try:
        return request.getfixturevalue(f'{request.param}_p_factory')
    except pytest.FixtureLookupError:
        msg = f'Plugin or library "{request.param}" is not installed'
        pytest.skip(msg)


@pytest.mark.parametrize(
    ('sort_by', 'expected'),
    [
        (None, [[1, 2], [3, 4], [5], [3, 4], [1, 2]]),
        ('id', [[1, 2], [3, 4], [5], [3, 4], [1, 2]]),
        ('-id', [[5, 4], [3, 2], [1], [3, 2], [5, 4]]),
    ],
    ids=['default', 'asc', 'desc'],
)
async def test_sort_by_one_field(sort_by, expected, p_factory: LogPaginatorFactory[Any]):
    # arrange
    for i in range(1, 6):
        await p_factory.create_log(i, 'a')

    paginate = partial(p_factory.paginate, sort_fields=sort_by)
    # act
    results: list[list[Any]] = []

    def add(page) -> None:
        results.append(page.rows)

    p1 = await paginate()
    add(p1)
    assert p1.prev is None
    assert p1.next is not None

    p2 = await paginate(after=p1.next)
    add(p2)
    assert p2.prev is not None
    assert p2.next is not None

    p3 = await paginate(after=p2.next)
    add(p3)
    assert p3.prev is not None
    assert p3.next is None

    p4 = await paginate(before=p3.prev)
    add(p4)
    assert p4.prev is not None
    assert p4.next is not None

    p5 = await paginate(before=p4.prev)
    add(p5)
    assert p5.prev is None
    assert p5.next is not None
    # assert
    assert _get_ids(results) == expected


@pytest.mark.parametrize(
    ('sort_by', 'expected'),
    [
        ('action,created', [[1, 2], [5, 6], [3, 4], [5, 6], [1, 2]]),
        ('-action,created', [[4, 3], [6, 5], [2, 1], [6, 5], [4, 3]]),
    ],
)
async def test_sort_by_multiple_fields(
    sort_by,
    expected,
    p_factory: LogPaginatorFactory[Any],
):
    create_log = p_factory.create_log
    [await create_log(i, '') for i in range(1, 3)]
    [await create_log(i, 'B') for i in range(3, 5)]
    [await create_log(i, 'A') for i in range(5, 7)]

    results = []

    def add(page) -> None:
        results.append(page.rows)

    paginate = partial(p_factory.paginate, sort_fields=sort_by)

    p1 = await paginate()
    add(p1)
    assert p1.prev is None
    assert p1.next is not None

    p2 = await paginate(after=p1.next)
    add(p2)
    assert p2.prev is not None
    assert p2.next is not None

    p3 = await paginate(after=p2.next)
    add(p3)
    assert p3.prev is not None
    assert p3.next is None

    p4 = await paginate(before=p3.prev)
    add(p4)
    assert p4.prev is not None
    assert p4.next is not None

    p5 = await paginate(before=p4.prev)
    add(p5)
    assert p5.prev is None
    assert p5.next is not None

    assert _get_ids(results) == expected


async def test_empty_store(p_factory: LogPaginatorFactory[Any]):
    # act
    page = await p_factory.paginate()
    # assert
    assert list(page.rows) == []
    assert page.prev is None
    assert page.next is None


async def test_consistency_on_data_remove(p_factory: LogPaginatorFactory[Any]):
    # arrange
    _, log_2, log_3, _, _ = [await p_factory.create_log(i) for i in range(1, 6)]
    # act
    p1 = await p_factory.paginate()
    for log in (log_2, log_3):
        await p_factory.rm_log(log)
    p2 = await p_factory.paginate(after=p1.next)
    # assert
    assert _rows_to_ids(p2.rows) == [4, 5]
    assert p2.prev is None
    assert p2.next is None


@pytest.mark.parametrize(
    ('size', 'expected'),
    [
        (-1, [1]),
        (-999, [1]),
        (None, [1, 2]),
        (0, [1]),
        (1, [1]),
        (6, [1, 2, 3]),
        (1_000, [1, 2, 3]),
    ],
)
async def test_size_param(size, expected, p_factory: LogPaginatorFactory[Any]):
    # arrange
    for i in range(1, 6):
        await p_factory.create_log(i)
    # act
    page = await p_factory.paginate(size=size)
    # assert
    assert _rows_to_ids(page.rows) == expected


async def test_null_cursor():
    # arrange
    p = InMemoryCursorPaginator[Any](
        unq_field='id',
        default_sort='null,id',
        sort_fields={'id': 'id', 'null': 'null'},
    )
    # act
    with pytest.raises(CursorValueErr):
        await p.paginate([{'id': 1, 'null': None}, {'id': 2, 'null': None}], size=1)


@pytest.mark.parametrize(
    'data',
    [
        [{'id': 1, 'action': ''}, {'id': 2, 'action': ''}],
        [object(), object()],
    ],
)
async def test_invalid_data_attrs(data):
    # arrange
    p = InMemoryCursorPaginator[Any](
        unq_field='id',
        default_sort='act,id',
        sort_fields={'id': 'id', 'act': 'act'},
    )
    # act
    with pytest.raises(PaginationErr):
        await p.paginate(data, size=1)


def test_init__no_unq_field_in_sort_fields():
    # act
    with pytest.raises(ConfigurationErr):
        InMemoryCursorPaginator(
            unq_field='id',
            sort_fields={'act': 'act'},
        )


@pytest.mark.parametrize(
    ('default_size', 'max_size'),
    [
        (0, None),
        (-100, None),
        (10, 9),
    ],
    ids=['default_size=0', 'default_size=-100', 'default_size>max_size'],
)
def test_init__invalid_default_size(default_size, max_size):
    # act
    with pytest.raises(ConfigurationErr):
        InMemoryCursorPaginator(
            unq_field='id',
            sort_fields={'id': 'id'},
            default_size=default_size,
            max_size=max_size,
        )


@pytest.mark.parametrize('max_size', [0, -100])
def test_init__invalid_max_size(max_size):
    # act
    with pytest.raises(ConfigurationErr):
        InMemoryCursorPaginator(
            unq_field='id',
            sort_fields={'id': 'id'},
            max_size=max_size,
        )


async def test_pagination_with_cursor_from_another_paginator():
    p = InMemoryCursorPaginator[Any](
        unq_field='id',
        sort_fields={'id': 'id'},
    )
    p_next = InMemoryCursorPaginator[Any](
        unq_field='id',
        default_sort='act,id',
        sort_fields={'id': 'id', 'act': 'act'},
    )
    # act
    page = await p.paginate([{'id': 1, 'act': ''}, {'id': 2, 'act': ''}], size=1)
    with pytest.raises(CursorValueErr):
        await p_next.paginate([], after=page.next)


@pytest.mark.parametrize('param', ['after', 'before'])
async def test_pagination_with_multiple_sort__err(param, p_factory):
    # arrange
    cursor = base64.b64encode(b'1')
    sort_fields = 'action,created'
    # act
    with pytest.raises(CursorValueErr):
        await p_factory.paginate(sort_fields=sort_fields, **{param: cursor})


async def test_multiple_cursor__err(p_factory):
    # arrange
    cursor = base64.b64encode(b'1')
    # act
    with pytest.raises(MultipleCursorsErr) as exc:
        await p_factory.paginate(before=cursor, after=cursor)
    # Assert
    assert exc.value.title == 'Multiple cursors error'
    assert exc.value.detail == 'Only one cursor can be used in a query'


async def test_cursor_param__err(p_factory):
    # act
    with pytest.raises(CursorParamsErr) as exc:
        await p_factory.paginate(sort_fields='id,created')
    # assert
    assert exc.value.detail == 'Move "id" field to the end'


@pytest.mark.parametrize('param', ['after', 'before'])
async def test_cursor_param__incorrect_value(param, p_factory):
    # act
    with pytest.raises(CursorValueErr) as exc:
        await p_factory.paginate(**{param: 'bad_value'})
    # assert
    assert exc.value.detail == 'Invalid base64 value'


@pytest.mark.parametrize('param', ['after', 'before'])
async def test_cursor_param__invalid_cursor_type(param, p_factory):
    # arrange
    cursor = base64.urlsafe_b64encode(b'bad_value')
    # act
    with pytest.raises(CursorValueErr) as exc:
        await p_factory.paginate(**{param: cursor})
    # assert
    assert exc.value.detail == 'Invalid cursor value'


def _get_ids(all_rows: list[list[Any]]) -> list[list[int]]:
    return [_rows_to_ids(rows) for rows in all_rows]


def _rows_to_ids(rows: list[Any]) -> list[int]:
    return [cast(int, row.id) for row in rows]
