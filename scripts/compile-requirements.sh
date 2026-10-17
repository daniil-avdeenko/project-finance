#!/usr/bin/env bash
set -euo pipefail

docker build -t pf-pip-tools -f scripts/requirements-compile.Dockerfile .

docker run --rm -v "$(pwd):/app" pf-pip-tools bash -c "\
    pip-compile --no-emit-index-url --no-emit-trusted-host requirements.in && \
    pip-compile --no-emit-index-url --no-emit-trusted-host requirements-dev.in"

echo "Lock files updated: requirements.txt, requirements-dev.txt"
