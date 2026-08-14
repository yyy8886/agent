# Network Requirements

Read this reference only for the fallback CLI mode. The bundled CLI calls the OpenAI Image API
and therefore requires outbound network access and `OPENAI_API_KEY`.

Use the application's normal permission and network policy. Do not assume that a command-line
flag enables network access; deployment, sandbox, firewall, and container settings control it.

Before enabling unattended networked commands, confirm that the repository and command are
trusted. Reducing approval prompts lowers friction but also reduces the opportunity to inspect
networked operations.
