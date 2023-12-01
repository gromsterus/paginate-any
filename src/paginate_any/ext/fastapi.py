from contextlib import suppress
from typing import Any, Protocol, TypeVar

import fastapi
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import HTTPException
from pydantic import PositiveInt
from starlette.responses import JSONResponse

from paginate_any.cursor_pagination import CursorPaginator, FieldT, RowsStoreT, RowT
from paginate_any.exc import check_module_version
from paginate_any.rest_api import (
    Error,
    JsonCursorPagination,
    PaginationConf,
    PaginationResult,
    UrlParts,
)


__all__ = [
    'FastApiPaginationException',
    'FastApiCursorPagination',
    'init_paginate_any_fastapi_app',
    'PaginationDependProtocol',
]


check_module_version('fastapi', fastapi.__version__, (0, 100))


class FastApiPaginationException(HTTPException):
    def __init__(
        self,
        errors: list[Error] | None = None,
        status_code: int = 400,
        message: str = 'Pagination errors',
        headers: dict[str, Any] | None = None,
    ):
        super().__init__(status_code, message, headers)
        self.errors = errors or []


_T_contra = TypeVar('_T_contra', contravariant=True)
_R = TypeVar('_R')


class PaginationDependProtocol(Protocol[_T_contra, _R]):
    async def paginate(
        self,
        store: _T_contra,
    ) -> PaginationResult[_R]:  # pragma: no cover
        ...


class FastApiCursorPagination(
    JsonCursorPagination[Request, FieldT, RowsStoreT, RowT],
):
    def _get_query_params(self, req: Request) -> str:
        return req.url.query

    def _get_url_parts_from_request(self, req: Request) -> UrlParts:
        base_url = req.base_url
        scheme = req.headers.get('X-Forwarded-Proto') or base_url.scheme

        host = base_url.hostname
        if fwd_host := req.headers.get('X-Forwarded-Host'):
            host = str(fwd_host)
            port = None
        else:
            port = base_url.port

        if fwd_port := req.headers.get('X-Forwarded-Port'):
            with suppress(ValueError):
                port = int(str(fwd_port))

        return UrlParts(scheme, host, port, req.url.path)

    def _to_framework_error(
        self,
        _: Request,
        errors: list[Error],
    ) -> FastApiPaginationException:
        raise FastApiPaginationException(errors)

    @classmethod
    def depend(
        cls,
        paginator: CursorPaginator[FieldT, RowsStoreT, RowT],
        conf: PaginationConf | None = None,
    ) -> type[PaginationDependProtocol[RowsStoreT, RowT]]:
        p = cls(paginator, conf)
        c = p.conf

        class PaginationDepend(PaginationDependProtocol[RowsStoreT, RowT]):
            """FastAPI dependency with aliases for doc generation."""

            def __init__(  # noqa: PLR0913
                self,
                request: Request,
                # fake spec for openapi doc
                sort: str | None = Query(paginator.default_sort, alias=c.sort_param),
                size: PositiveInt = Query(paginator.default_size, alias=c.size_param),
                before: str | None = Query(None, alias=c.before_param),
                after: str | None = Query(None, alias=c.after_param),
            ):
                self._req = request

            async def paginate(self, store: RowsStoreT) -> PaginationResult[RowT]:
                return await p.paginate(self._req, store)

        return PaginationDepend


def fastapi_pagination_exc_handler(
    _: Request,
    exception: FastApiPaginationException,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={'errors': [e.to_dict() for e in exception.errors]},
    )


def init_paginate_any_fastapi_app(app: FastAPI) -> None:
    app.add_exception_handler(FastApiPaginationException, fastapi_pagination_exc_handler)
