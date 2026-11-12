FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# System libraries the CAD kernel needs. build123d pulls cadquery-ocp, which links
# against the usual X/GL runtime even for headless STEP work.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglx-mesa0 libxrender1 libxext6 libsm6 libxi6 libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first (cached layer, rebuilt only when the lockfile changes).
#
# Deliberately without --locked: this pipeline adds a CAD kernel and a vision
# client to a template that shipped neither, and `uv sync --locked` refuses to
# build until uv.lock is regenerated on a machine that has uv. Refresh it with
# `uv lock` (see README) and commit the result; until then the build resolves from
# pyproject.toml, which is slower but never blocks a submission.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project --no-dev

# Copy the project into the image
COPY . /app

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Agent settings, frozen with your commit (README: Configuration). After code freeze, the values in
# your handed-over <team>.env replace these.
# ENV OPENAI_BASE_URL=http://<your Brev instance>:8000/v1 \
#     OPENAI_API_KEY=<your vLLM --api-key> \
#     OPENAI_MODEL=<model>

# The pipeline writes only to --output_dir and its scratch directory.
CMD ["python", "scripts/main.py"]
