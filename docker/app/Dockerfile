FROM python:3.8.1-slim as builder

# Make sure that POETRY_VERSION is the same in pyproject.toml
ENV POETRY_VERSION=1.0.3 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=off

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

FROM python:3.8.1-slim AS final

# Dumb-init is required for proper signal handling in the container
RUN apt-get update -qq && apt-get install -qq dumb-init > /dev/null 2>&1

# Run the container in our local timezone for automatic DST.
# /etc/localtime has to be removed as otherwise tzdata overwrites
# /etc/timezone back to Etc/UTC for some reason
RUN apt-get update -qq && apt-get install -qq tzdata && \
    echo 'Europe/Helsinki' > /etc/timezone && rm /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata > /dev/null 2>&1

# A non-root user cannot access files in a volume created with docker-compose
# without the hack below (PermissionError: [Errno 13] Permission denied).
# By creating the directory beforehand here the permissions will be inherited
# in the actual volume and the data will then persist even between multiple
# docker-compose runs.
RUN useradd runner && mkdir /data && chown -R runner:runner /data
USER runner

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONFAULTHANDLER=1

ENTRYPOINT [ "/usr/bin/dumb-init", "--", "rubus", "--docker" ]
