FROM python:3.7.5-slim as builder

# Make sure that POETRY_VERSION is the same in pyproject.toml
ENV POETRY_VERSION=1.0.0 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=off

# A non-root user cannot access files in a volume created with docker-compose
# without the hack below (PermissionError: [Errno 13] Permission denied).
# By creating the directory beforehand here the permissions will be inherited
# in the actual volume and the data will then persist even between multiple
# docker-compose runs.
RUN useradd runner && mkdir /data && chown -R runner:runner /data

# Install everything into a virtualenv for multi-stage building
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip install --quiet "poetry==$POETRY_VERSION"

# Install the dependencies separately into the venv first
WORKDIR /temp/install
COPY poetry.lock pyproject.toml ./
RUN poetry export -f requirements.txt | pip install --quiet -r /dev/stdin

# A pure poetry install would not actually install rubus, but instead create
# a link to the egg. Therefore, build the wheel separately and install it
# using pip. Afterwards rubus is actually installed also within the venv!
COPY rubus ./rubus
RUN poetry build --quiet && pip install --no-dependencies ./dist/rubus-*py3-none-any.whl

FROM python:3.7.5-slim AS final

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# De-elevate from root for security
USER runner
ENTRYPOINT [ "rubus", "--docker" ]
