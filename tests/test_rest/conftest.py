import sys
from string import ascii_uppercase
from typing import Any

import msgspec.json
import pytest

from paginate_any.cursor_pagination import InMemoryCursorPaginator
from paginate_any.rest_api import PaginationConf

from ._store import Car


@pytest.fixture()
def fastapi_fab(paginator, store):
    try:
        from fastapi import FastAPI, Request
        from httpx import AsyncClient
    except ImportError as e:
        pytest.skip(str(e))

    from paginate_any.ext.fastapi import (
        FastApiCursorPagination,
        init_paginate_any_fastapi_app,
    )

    def wrap(conf: PaginationConf | None = None) -> tuple[FastAPI, AsyncClient]:
        app = FastAPI()
        init_paginate_any_fastapi_app(app)

        @app.get('/')
        async def paginate(request: Request):
            pagination = FastApiCursorPagination(paginator, conf)
            pagination_result = await pagination.paginate(request, store)
            resp = pagination_result.json_resp()
            return resp

        return app, AsyncClient(app=app, base_url='https://app')

    return wrap


@pytest.fixture()
def sanic_fab(paginator, store):
    try:
        import httpx
        from sanic import Sanic, response
        from sanic_testing.testing import SanicASGITestClient, TestingResponse
    except ImportError as e:
        pytest.skip(str(e))

    class _SanicASGITestClient(SanicASGITestClient):
        async def request(self, *args, **kwargs) -> TestingResponse | None:
            req, resp = await super().request(*args, **kwargs)
            resp.__class__ = httpx.Response
            return resp

    from paginate_any.ext.sanic import (
        SanicJsonCursorPagination,
        init_paginate_any_sanic_app,
    )

    def wrap(
        conf: PaginationConf | None = None,
    ) -> tuple[Sanic[Any, Any], SanicASGITestClient]:
        app = Sanic('test_app')
        app.config.FALLBACK_ERROR_FORMAT = 'json'
        app.config.PROXIES_COUNT = 1
        app.config.TOUCHUP = False
        app.config.REQUEST_TIMEOUT = sys.maxsize
        app.config.RESPONSE_TIMEOUT = sys.maxsize
        init_paginate_any_sanic_app(app)

        @app.get('/')
        async def paginate(request):
            pagination = SanicJsonCursorPagination(paginator, conf)
            pagination_result = await pagination.paginate(request, store)
            res = pagination_result.json_resp()
            return response.raw(msgspec.json.encode(res))

        return app, _SanicASGITestClient(app)

    return wrap


@pytest.fixture()
def paginator():
    return InMemoryCursorPaginator(
        'id',
        sort_fields={'id': 'id'},
        default_size=2,
    )


@pytest.fixture()
def store():
    return [Car(id=i, name=ascii_uppercase[-i]) for i in range(1, 6)]
