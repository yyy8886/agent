---
name: environment-memory
description: Inspect and safely report this application's current runtime environment, including host and actual execution platform, shell, Python executable, normalized workspace paths, available commands, filesystem capabilities, and selected non-secret environment configuration. Use when diagnosing Windows/WSL/Linux compatibility, preparing deployment, debugging tool failures, or reading the operating environment or environment variables. Never expose secret values.
---

# Environment Memory

Use the bundled `scripts/inspect_environment.py` script as the source of truth. Run it before environment-sensitive work and when a tool fails unexpectedly.

The script is read-only. It reports JSON with: host and actual runtime platform, shell, Python executable/version, current directory, normalized path information, command availability, file read/write checks, and a redacted environment-variable inventory.

Rules:

1. Treat the actual command runtime separately from the host OS. WSL may report a Linux runtime on a Windows host.
2. Use reported `path_forms` and `workspace` values; do not manually convert `C:\...` to `/mnt/c/...`.
3. Never print or return secret values. Variables whose names contain `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, or `AUTH` are reported only as `configured: true/false`.
4. Do not read arbitrary environment variables unless the user explicitly names a variable and it is not secret.
5. If a capability is unavailable, report it and choose a supported fallback. Do not retry commands using a different shell merely by guessing.
6. Include the JSON report or a concise summary in the final answer, especially when a compatibility issue explains a failure.

For deployment, run the same script inside the target Linux container or service account. Compare the report rather than relying on the development machine's report.
