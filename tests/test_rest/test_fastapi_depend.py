from typing import Annotated

from paginate_any.rest_api import JsonPaginationResp

from ._store import Car


async def test_fastapi_pagination_depend(fastapi_fab, paginator, store):
    from fastapi import Depends, FastAPI
    from paginate_any.ext.fastapi import FastApiCursorPagination, PaginationDependProtocol
    from pydantic import BaseModel, ConfigDict

    class CarModel(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        id: int
        name: str

    app: FastAPI
    app, cli = fastapi_fab()

    @app.get('/cars', response_model=JsonPaginationResp[CarModel])
    async def paginate(
        p: Annotated[
            PaginationDependProtocol[list[Car], Car],
            Depends(FastApiCursorPagination.depend(paginator)),
        ],
    ):
        result = await p.paginate(store)
        return result.json_resp()

    resp = await cli.get('/cars')
    assert resp.status_code == 200, resp.content
