[![python version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![formatter black](https://img.shields.io/badge/Formatter-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# PaginateAny

Pagination primitives for any ORM and web-frameworks.

## Known issues
* Decode and Encode of a cursor values hardcoded with `msgspec.msgpack` module.
  You can't use timezone-naive datetime format, because it converts value to the `str` type.
  See [spec](https://jcristharif.com/msgspec/supported-types.html) and 
  [issue](https://github.com/jcrist/msgspec/issues/336#issuecomment-1481260377) about 
  supported types.

## Code example

```python
from typing import Annotated
from datetime import datetime, timezone

from fastapi import FastAPI, Depends
from paginate_any.cursor_pagination import InMemoryCursorPaginator
from paginate_any.ext.fastapi import (
    FastApiCursorPagination,
    PaginationDependProtocol,
    init_paginate_any_fastapi_app,
)
from paginate_any.rest_api import JsonPaginationResp
from pydantic import BaseModel

app = FastAPI()
init_paginate_any_fastapi_app(app)


class Car(BaseModel):
    id: int
    name: str
    factory_start: datetime


paginator = InMemoryCursorPaginator[Car](
    unq_field='id',
    sort_fields={
      'id': 'id',
      'factory_start': 'factory_start',
    },
    default_size=2,
)
store = [
    Car(id=1, name='BMW', factory_start=datetime(1916, 3, 7, tzinfo=timezone.utc)),
    Car(id=2, name='Audi', factory_start=datetime(1909, 7, 16, tzinfo=timezone.utc)),
    Car(id=3, name='Mercedes-Benz', factory_start=datetime(1926, 6, 28, tzinfo=timezone.utc)),
    Car(id=4, name='Volkswagen', factory_start=datetime(1937, 5, 28, tzinfo=timezone.utc)),
    Car(id=5, name='Porsche', factory_start=datetime(1931, 4, 25, tzinfo=timezone.utc)),
]


@app.get('/cars', response_model=JsonPaginationResp[Car])
async def cars(
    p: Annotated[
        PaginationDependProtocol[list[Car], Car],
        Depends(FastApiCursorPagination.depend(paginator)),
    ],
):
    result = await p.paginate(store)
    return result.json_resp()

```
Request:
```shell
curl -X GET "http://127.0.0.1:8000/cars?ordering=factory_start" -H  "accept: application/json"
```
Response:
```json
{
  "pagination": {
    "size": 2,
    "after": "kscM_wAAAAD_____msOxAAE="
  },
  "links": {
    "next": "http://127.0.0.1:8000/cars?after=kscM_wAAAAD_____msOxAAE%3D&ordering=factory_start"
  },
  "data": [
    {
      "id": 2,
      "name": "Audi",
      "factory_start": "1909-07-16T00:00:00Z"
    },
    {
      "id": 1,
      "name": "BMW",
      "factory_start": "1916-03-07T00:00:00Z"
    }
  ]
}
```
