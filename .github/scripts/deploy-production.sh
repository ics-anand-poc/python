#!/usr/bin/env bash
# Back-compat alias for older workflow filenames.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy-prod.sh"
