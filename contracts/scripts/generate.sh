#!/usr/bin/env bash
# Regenerate shared types from the frozen JSON Schemas (single source of truth):
#   contracts/ts/dso-contracts.ts                      -> Stream 1 (frontend)
#   contracts/python/dso_contracts/models.py           -> Stream 2 (backend) + Stream 3 (pipeline)
# Needs: node/npx, and the tools venv (see README: .venv-tools).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${TOOLS_PY:-../.venv-tools/bin/python}"
python3 scripts/bundle_schemas.py
npx --yes json-schema-to-typescript@15 -i build/dso.bundle.schema.json -o ts/dso-contracts.ts \
  --unreachableDefinitions --additionalProperties false \
  --bannerComment "/* GENERATED from contracts/schemas/*.json by contracts/scripts/generate.sh. DO NOT EDIT. FROZEN v1.0 */"
"$(dirname "$PY")/datamodel-codegen" --input build/dso.bundle.schema.json --input-file-type jsonschema \
  --output python/dso_contracts/models.py --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.11 --use-standard-collections --use-union-operator \
  --field-constraints --collapse-root-models --use-double-quotes --disable-timestamp \
  --custom-file-header "# GENERATED from contracts/schemas/*.json by contracts/scripts/generate.sh. DO NOT EDIT. FROZEN v1.0"
echo "generated ts/dso-contracts.ts and python/dso_contracts/models.py"
