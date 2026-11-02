FROM python:3.12-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir hatchling
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim
RUN useradd --uid 10001 --create-home hive
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
USER 10001
