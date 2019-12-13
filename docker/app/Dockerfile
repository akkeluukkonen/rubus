FROM python:3.7.5-slim as builder

# Make sure that POETRY_VERSION is the same in pyproject.toml
ENV POETRY_VERSION=0.12.17 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=off

RUN useradd --create-home runner
# A non-root user cannot access files in a volume created with docker-compose
# without the hack below (PermissionError: [Errno 13] Permission denied).
# By creating the directory beforehand here the permissions will be inherited
# in the actual volume and the data will then persist even between multiple
# docker-compose runs.
RUN mkdir /data && chown -R runner:runner /data

# Install everything into a virtualenv for multi-stage building
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip install --quiet "poetry==$POETRY_VERSION"
RUN poetry config settings.virtualenvs.create false

# Install the dependencies separately into the venv first
WORKDIR /temp/install
COPY poetry.lock pyproject.toml /temp/install/
RUN poetry install --no-interaction --no-ansi --no-dev --quiet

# A pure poetry install would not actually install rubus, but instead create
# a link to the egg. Therefore, build the wheel separately and install it
# using pip. Afterwards rubus is actually installed also within the venv!
COPY rubus /temp/install/rubus
RUN poetry build && pip install --no-dependencies ./dist/rubus-*py3-none-any.whl

FROM python:3.7.5-slim AS final

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /home/runner/

# De-elevate from root for security
USER runner
ENTRYPOINT [ "rubus", "--docker" ]
