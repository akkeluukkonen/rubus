FROM python:3.7.4-buster

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ARG poetry_version
RUN pip install "poetry==$poetry_version"

WORKDIR /temp/install/
COPY poetry.lock pyproject.toml /temp/install/
RUN poetry config settings.virtualenvs.create false
RUN poetry install --no-interaction --no-ansi

RUN useradd --create-home appuser
WORKDIR /home/appuser
USER appuser

COPY ./rubus /home/appuser/rubus
ENTRYPOINT [ "python", "/home/appuser/rubus/main.py" ]
