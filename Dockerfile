# Dockerfile — CPU-only base image for segfacet (item 066).
#
# Builds a slim, CPU-only image of the segfacet pipeline pinned against the
# committed constraints.txt lockfile, with the bundled default reference
# artifact (src/segfacet/reference/reference_default.json) shipped as package
# data inside the installed wheel (no separate COPY needed for it — see
# segfacet.reference.artifact.default_artifact_path).
#
# This image deliberately sets NO ENTRYPOINT: item 068 layers the XNAT entry
# script on top of this base. `docker run <image> segfacet <args>` invokes the
# `segfacet` console script directly.
#
# Default build (no radiomics extra):
#   docker build -t segfacet:latest .
#
# Radiomics-enabled variant (adds the optional `pyradiomics`/SimpleITK extra):
#   docker build -t segfacet:radiomics --build-arg INSTALL_RADIOMICS=1 .

FROM python:3.11-slim

# CPU-only, no GPU/CUDA base layers or packages anywhere in this image.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build ARG toggling the optional radiomics extra. Default is off (AC5): the
# unconditional install line below never references [radiomics]. Set to a
# truthy value (e.g. 1/true) at build time to install the radiomics-enabled
# variant instead: `docker build --build-arg INSTALL_RADIOMICS=1 .`
ARG INSTALL_RADIOMICS=0

# Copy only what's needed to resolve/install the package first (better layer
# caching), respecting .dockerignore for the rest of the build context.
COPY pyproject.toml constraints.txt README.md ./
COPY src/ ./src/
# item 068: the XNAT Container Service entry script -- lands at the pinned
# in-image path /app/docker/entrypoint.py that item 067's command.json invokes.
COPY docker/ /app/docker/

RUN python -m pip install --upgrade pip \
    && pip install -c constraints.txt . \
    && if [ "$INSTALL_RADIOMICS" = "1" ] || [ "$INSTALL_RADIOMICS" = "true" ]; then \
         pip install .[radiomics]; \
       fi

# Non-root user for XNAT-host friendliness.
RUN useradd --create-home --shell /bin/bash segfacet
USER segfacet

# Ergonomic default; does not interfere with `docker run <image> segfacet <args>`.
CMD ["segfacet", "--help"]
