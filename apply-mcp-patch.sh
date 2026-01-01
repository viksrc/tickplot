#!/bin/bash
# Apply the mcp-run-python patch after reinstalling the package

set -e

# Find the mcp-run-python installation directory
MCP_DIR=$(python3 -c "import mcp_run_python; from pathlib import Path; print(Path(mcp_run_python.__file__).parent)")

if [ -z "$MCP_DIR" ]; then
    echo "Error: Could not find mcp-run-python installation"
    exit 1
fi

echo "Found mcp-run-python at: $MCP_DIR"

# Apply the patch
cd "$MCP_DIR"
patch -p1 < "$(dirname "$0")/mcp-run-python.patch"

# Remove lock file to force Deno to re-resolve dependencies
rm -f deno/deno.lock

echo "✓ Patch applied successfully!"
