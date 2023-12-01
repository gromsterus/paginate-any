import abc
from dataclasses import dataclass, fields
from functools import partial
from typing import (
    Final,
    Generic,
    NamedTuple,
    TypeAlias,
    TypeVar,
)
from urllib import parse
from urllib.parse import parse_qs, urlunparse

# TypedDict reason: https://docs.pydantic.dev/2.5/errors/usage_errors/#typed-dict-version
from typing_extensions import NotRequired, Required, TypedDict

from paginate_any.cursor_pagination import CursorPaginator, FieldT, RowsStoreT, RowT
from paginate_any.datastruct import CursorPaginationPage, DictStrAny
from paginate_any.exc import (
    CursorParamsErr,
    CursorValueErr,
    MultipleCursorsErr,
    SortParamErr,
)


__all__ = [
    'ErrSourcePointer',
    'ErrSourceParameter',
    'ErrSourceHeader',
    'Error',
    'JsonCursorPagination',
    'JsonCursorPagination',
    'JsonCursorPagination',
    'PaginationResult',
    'JsonPaginationResp',
    'QueryParamsT',
    'ReqT',
    'UrlParts',
    'PaginationConf',
    'set_default_conf',
]


_HTTP_SCHEMAS: Final = {'http', 'ws'}
_HTTPS_SCHEMAS: Final = {'https', 'wss'}
_HTTP_DEFAULT_PORT: Final = 80
_HTTPS_DEFAULT_PORT: Final = 443


class ErrSourcePointer(TypedDict):
    pointer: str


class ErrSourceParameter(TypedDict):
    parameter: str


class ErrSourceHeader(TypedDict):
    header: str


@dataclass(slots=True)
class Error:
    code: str | None = None
    title: str | None = None
    detail: str | None = None
    source: ErrSourcePointer | ErrSourceParameter | ErrSourceHeader | None = None

    def to_dict(self) -> DictStrAny:
        return {
            f.name: v for f in fields(self) if (v := getattr(self, f.name)) is not None
        }


class UrlParts(NamedTuple):
    scheme: str
    host: str | None
    port: int | None
    path: str


@dataclass(frozen=True, slots=True)
class PaginationConf:
    sort_param: str = 'ordering'
    size_param: str = 'size'
    before_param: str = 'before'
    after_param: str = 'after'


_default_conf = PaginationConf()


def set_default_conf(conf: PaginationConf) -> None:
    global _default_conf  # noqa: PLW0603
    _default_conf = conf


class Links(TypedDict):
    prev: NotRequired[str]
    next: NotRequired[str]


class Pagination(TypedDict):
    size: Required[int]
    before: NotRequired[str]
    after: NotRequired[str]


DataT = TypeVar('DataT')


class JsonPaginationResp(TypedDict, Generic[DataT]):
    pagination: Pagination
    links: Links
    data: list[DataT]


@dataclass(frozen=True, slots=True)
class PaginationResult(Generic[RowT]):
    page: CursorPaginationPage[RowT]
    conf: 'PaginationConf'
    prev_link: str | None = None
    next_link: str | None = None

    def json_resp(self) -> JsonPaginationResp[RowT]:
        resp: JsonPaginationResp[RowT] = {
            'data': self.page.rows,
            'pagination': {
                'size': self.page.cursor_params.size,
            },
            'links': {},
        }
        p = resp['pagination']
        if self.page.prev:
            p['before'] = self.page.prev
        if self.page.next:
            p['after'] = self.page.next

        links = resp.setdefault('links', {})
        if self.prev_link:
            links['prev'] = self.prev_link
        if self.next_link:
            links['next'] = self.next_link

        return resp


ReqT = TypeVar('ReqT')
QueryParamsT: TypeAlias = dict[str, list[str]]


class JsonCursorPagination(
    Generic[ReqT, FieldT, RowsStoreT, RowT],
    metaclass=abc.ABCMeta,
):
    __slots__ = (
        '_paginator',
        '_conf',
    )

    def __init__(
        self,
        paginator: CursorPaginator[FieldT, RowsStoreT, RowT],
        conf: PaginationConf | None = None,
    ):
        self._paginator = paginator
        self._conf = conf

    @property
    def conf(self) -> PaginationConf:
        return self._conf or _default_conf

    async def paginate(
        self,
        req: ReqT,
        store: RowsStoreT,
    ) -> PaginationResult[RowT]:
        c = self.conf
        params: QueryParamsT = {}
        if params_str := self._get_query_params(req):
            params = parse_qs(
                params_str,
                keep_blank_values=True,
                strict_parsing=True,
            )

        get = partial(self._get_param_val, params)
        sort_fields = get(c.sort_param)
        before, after = get(c.before_param), get(c.after_param)
        try:
            size = int(v) if (v := get(c.size_param)) else None
        except (ValueError, TypeError) as exc:
            err = Error(
                title='Must be a valid integer',
                source=ErrSourceParameter(parameter=c.size_param),
            )
            raise self._to_framework_error(req, [err]) from exc

        try:
            page = await self._paginator.paginate(store, sort_fields, before, after, size)
        except CursorParamsErr as exc:
            errors = self._pagination_err_to_api_err(exc, before, after)
            raise self._to_framework_error(req, errors) from exc

        path = self._get_request_path(req)

        def gen_link(param: str, value: str) -> str:
            return self._generate_url(path, {param: [value], **params})

        params.pop(c.before_param, None)
        params.pop(c.after_param, None)
        result: PaginationResult[RowT] = PaginationResult(
            page=page,
            conf=c,
            prev_link=gen_link(c.before_param, page.prev) if page.prev else None,
            next_link=gen_link(c.after_param, page.next) if page.next else None,
        )
        return result

    @staticmethod
    def _get_param_val(params: QueryParamsT, key: str) -> str | None:
        """Return first query param value."""
        return val[0] if (val := params.get(key)) else None

    @abc.abstractmethod
    def _get_query_params(self, req: ReqT) -> str:
        pass

    @abc.abstractmethod
    def _get_url_parts_from_request(self, req: ReqT) -> UrlParts:
        pass

    def _get_request_path(self, req: ReqT) -> str:
        scheme, host, port, path = self._get_url_parts_from_request(req)
        if (
            host is None
            or port is None
            or (scheme in _HTTP_SCHEMAS and port == _HTTP_DEFAULT_PORT)
            or (scheme in _HTTPS_SCHEMAS and port == _HTTPS_DEFAULT_PORT)
        ):
            netloc = host
        else:
            netloc = f'{host}:{port}'

        return str(urlunparse((scheme, netloc, path, None, None, None)))

    @staticmethod
    def _generate_url(path: str, params: QueryParamsT) -> str:
        query_params = f'?{parse.urlencode(params, doseq=True)}' if params else ''
        return parse.urljoin(path, query_params)

    def _pagination_err_to_api_err(
        self,
        err: CursorParamsErr,
        before: str | None,
        after: str | None,
    ) -> list[Error]:
        c = self.conf
        errors: Error | list[Error]
        if isinstance(err, SortParamErr):
            errors = Error(
                title=err.title,
                source=ErrSourceParameter(parameter=c.sort_param),
            )
        elif isinstance(err, CursorValueErr):
            cursor_param = c.before_param if before else c.after_param
            errors = Error(
                title=err.title,
                source=ErrSourceParameter(parameter=cursor_param),
            )
        elif isinstance(err, MultipleCursorsErr):
            errors = [
                Error(
                    title=err.title,
                    source=ErrSourceParameter(parameter=p),
                )
                for p in (c.before_param, c.after_param)
            ]
        else:
            errors = Error(title=err.title)

        return errors if isinstance(errors, list) else [errors]

    @abc.abstractmethod
    def _to_framework_error(self, req: ReqT, errors: list[Error]) -> Exception:
        pass
