ARG py_version=3.12
FROM python:${py_version}

ENV PROJECT_ROOT=/app

WORKDIR $PROJECT_ROOT/
COPY requirements-build.txt $PROJECT_ROOT/requirements-build.txt
RUN --mount=type=cache,target=/root/.cache \
    pip install -U pip && pip install -r requirements-build.txt

ADD . $PROJECT_ROOT/

ARG extra=dev,dev-fastapi,dev-sanic,dev-sqlalchemy
RUN pip install -e .[$extra]
