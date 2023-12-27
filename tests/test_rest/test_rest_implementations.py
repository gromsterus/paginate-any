from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from paginate_any.exc import CursorParamsErr
from paginate_any.rest_api import PaginationConf, set_default_conf


if TYPE_CHECKING:
    from pytest_mock import MockerFixture


pytestmark = pytest.mark.filterwarnings('ignore::DeprecationWarning')


class AppFabReq(pytest.FixtureRequest):
    param: str


@pytest.fixture(params=['fastapi', 'sanic'])
@pytest.mark.filterwarnings('ignore::DeprecationWarning')
def app_fab(request: AppFabReq):
    return request.getfixturevalue(f'{request.param}_fab')


async def test_pagination(app_fab):
    app, cli = app_fab()

    resp = await cli.get('/', params={'a': ['1', '2'], 'b': '3'})
    assert resp.status_code == 200, resp.content
    assert resp.json() == {
        'data': [{'id': 1, 'name': 'Z'}, {'id': 2, 'name': 'Y'}],
        'links': {'next': f'{cli.base_url}/?after=kQI%3D&a=1&a=2&b=3'},
        'pagination': {'after': 'kQI=', 'size': 2},
    }

    next0_link = resp.json()['links']['next']
    next0_resp = await cli.get(
        next0_link,
        headers={
            'X-Forwarded-For': '1.1.1.1',
            'X-Forwarded-Proto': 'https',
            'X-Forwarded-Host': 'myapp',
            'X-Forwarded-Port': '9999',
        },
    )
    assert next0_resp.status_code == 200, next0_resp.content
    assert next0_resp.json() == {
        'data': [{'id': 3, 'name': 'X'}, {'id': 4, 'name': 'W'}],
        'links': {
            'next': 'https://myapp:9999/?after=kQQ%3D&a=1&a=2&b=3',
            'prev': 'https://myapp:9999/?before=kQM%3D&a=1&a=2&b=3',
        },
        'pagination': {'after': 'kQQ=', 'before': 'kQM=', 'size': 2},
    }

    next1_link = next0_resp.json()['links']['next']
    next1_resp = await cli.get(
        next1_link,
        headers={
            'X-Forwarded-For': '1.1.1.1',
            'X-Forwarded-Proto': 'https',
            'X-Forwarded-Host': 'myapp',
        },
    )
    assert next1_resp.status_code == 200, next1_resp.content
    assert next1_resp.json() == {
        'data': [{'id': 5, 'name': 'V'}],
        'links': {'prev': 'https://myapp/?before=kQU%3D&a=1&a=2&b=3'},
        'pagination': {'before': 'kQU=', 'size': 2},
    }


@pytest.fixture()
def global_conf():
    conf = PaginationConf(size_param='superSize')
    set_default_conf(conf)
    yield conf
    set_default_conf(PaginationConf())


async def test_set_default_conf(global_conf, app_fab):
    app, cli = app_fab()

    resp = await cli.get('/', params={global_conf.size_param: 1})

    assert resp.status_code == 200, resp.content
    assert len(resp.json()['data']) == 1


@pytest.mark.parametrize('param_name', ['page[size]', 'size'])
async def test_size_param_invalid(param_name, app_fab):
    app, cli = app_fab(conf=PaginationConf(size_param=param_name))

    resp = await cli.get('/', params={param_name: 'invalid'})

    assert resp.status_code == 400, resp.content
    assert resp.json() == {
        'errors': [
            {
                'source': {'parameter': param_name},
                'title': 'Must be a valid integer',
            },
        ],
    }


@pytest.mark.parametrize('param_name', ['sort', 'ordering'])
async def test_sort_param_invalid(param_name, app_fab):
    app, cli = app_fab(conf=PaginationConf(sort_param=param_name))

    resp = await cli.get('/', params={param_name: 'invalid'})

    assert resp.status_code == 400, resp.content
    assert resp.json() == {
        'errors': [
            {
                'source': {'parameter': param_name},
                'title': 'Invalid sort param',
            },
        ],
    }


@pytest.mark.parametrize('param_name', ['page[before]', 'before'])
async def test_before_param_invalid(param_name, app_fab):
    app, cli = app_fab(conf=PaginationConf(before_param=param_name))

    resp = await cli.get('/', params={param_name: 'invalid'})

    assert resp.status_code == 400, resp.content
    assert resp.json() == {
        'errors': [
            {
                'source': {'parameter': param_name},
                'title': 'Cursor value error',
            },
        ],
    }


@pytest.mark.parametrize('param_name', ['page[after]', 'after'])
async def test_after_param_invalid(param_name, app_fab):
    app, cli = app_fab(conf=PaginationConf(after_param=param_name))

    resp = await cli.get('/', params={param_name: 'invalid'})

    assert resp.status_code == 400, resp.content
    assert resp.json() == {
        'errors': [
            {
                'source': {'parameter': param_name},
                'title': 'Cursor value error',
            },
        ],
    }


async def test_multiple_cursors_err(app_fab):
    app, cli = app_fab()

    resp = await cli.get(
        '/',
        params={'before': 'a', 'after': 'b'},
    )

    assert resp.status_code == 400, resp.content
    assert resp.json() == {
        'errors': [
            {
                'source': {'parameter': f},
                'title': 'Multiple cursors error',
            }
            for f in ('before', 'after')
        ],
    }


async def test_any_cursor_params_err(paginator, app_fab, mocker: MockerFixture):
    app, cli = app_fab()
    mocker.patch.object(
        paginator,
        'paginate',
        side_effect=CursorParamsErr(title='Some error'),
    )

    resp = await cli.get('/')

    assert resp.status_code == 400, resp.content
    assert resp.json() == {'errors': [{'title': 'Some error'}]}
