$ErrorActionPreference = "Stop"

docker build -t pf-pip-tools -f scripts/requirements-compile.Dockerfile .

docker run --rm -v "${PWD}:/app" pf-pip-tools bash -c "pip-compile --no-emit-index-url --no-emit-trusted-host requirements.in && pip-compile --no-emit-index-url --no-emit-trusted-host requirements-dev.in"

Write-Host "Lock files updated: requirements.txt, requirements-dev.txt"
