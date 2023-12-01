from typing import Any

import sanic
from sanic import Sanic
from sanic.exceptions import SanicException
from sanic.request import Request
from sanic.response import HTTPResponse, json

from paginate_any.cursor_pagination import FieldT, RowsStoreT, RowT
from paginate_any.datastruct import DictStrAny
from paginate_any.exc import check_module_version
from paginate_any.rest_api import Error, JsonCursorPagination, UrlParts


__all__ = [
    'SanicPaginationException',
    'SanicJsonCursorPagination',
    'init_paginate_any_sanic_app',
]


check_module_version('sanic', sanic.__version__, (20, 12))

ReqT = Request[Any, Any]


class SanicPaginationException(SanicException):
    def __init__(  # noqa: PLR0913
        self,
        errors: list[Error] | None = None,
        message: str = 'Pagination errors',
        status_code: int = 400,
        *,
        quiet: bool | None = None,
        context: DictStrAny | None = None,
        extra: DictStrAny | None = None,
        headers: DictStrAny | None = None,
    ):
        super().__init__(
            message,
            status_code,
            quiet=quiet,
            context=context,
            extra=extra,
            headers=headers,
        )
        self.errors = errors or []


class SanicJsonCursorPagination(
    JsonCursorPagination[ReqT, FieldT, RowsStoreT, RowT],
):
    def _get_query_params(self, req: ReqT) -> str:
        return req.query_string

    def _get_url_parts_from_request(self, req: ReqT) -> UrlParts:
        scheme = req.scheme.lower()
        host = req.server_name
        port = req.server_port
        path = req.path

        return UrlParts(scheme, host, port, path)

    def _to_framework_error(
        self,
        _: ReqT,
        errors: list[Error],
    ) -> SanicPaginationException:
        raise SanicPaginationException(errors)


def sanic_pagination_exc_handler(
    _: Request[Any, Any],
    exception: SanicPaginationException,
) -> HTTPResponse:
    return json(
        {'errors': [e.to_dict() for e in exception.errors]},
        status=400,
    )


def init_paginate_any_sanic_app(app: Sanic[Any, Any]) -> None:
    app.error_handler.add(SanicPaginationException, sanic_pagination_exc_handler)
