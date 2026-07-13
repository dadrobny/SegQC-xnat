# Dockerfile — CPU-only base image for segqc (item 066).
#
# Builds a slim, CPU-only image of the segqc pipeline pinned against the
# committed constraints.txt lockfile, with the bundled default reference
# artifact (src/segqc/reference/reference_default.json) shipped as package
# data inside the installed wheel (no separate COPY needed for it — see
# segqc.reference.artifact.default_artifact_path).
#
# This image deliberately sets NO ENTRYPOINT: item 068 layers the XNAT entry
# script on top of this base. `docker run <image> segqc <args>` invokes the
# `segqc` console script directly.
#
# Default build (no radiomics extra):
#   docker build -t segqc:latest .
#
# Radiomics-enabled variant (adds the optional `pyradiomics`/SimpleITK extra):
#   docker build -t segqc:radiomics --build-arg INSTALL_RADIOMICS=1 .

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

RUN python -m pip install --upgrade pip \
    && pip install -c constraints.txt . \
    && if [ "$INSTALL_RADIOMICS" = "1" ] || [ "$INSTALL_RADIOMICS" = "true" ]; then \
         pip install .[radiomics]; \
       fi

# Non-root user for XNAT-host friendliness.
RUN useradd --create-home --shell /bin/bash segqc
USER segqc

# Ergonomic default; does not interfere with `docker run <image> segqc <args>`.
CMD ["segqc", "--help"]
