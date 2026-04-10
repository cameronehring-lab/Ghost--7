# OMEGA4 Repo Expert Tool

This repo now includes a local CLI for architecture orientation outside chat history.

Purpose:

- print a stable high-level description of what OMEGA4 is
- provide a recommended file read order
- group the codebase into operational slices
- trace a normal `POST /ghost/chat` turn end-to-end

Command:

```bash
python3 scripts/omega_expert_tool.py
```

Useful subcommands:

```bash
python3 scripts/omega_expert_tool.py overview
python3 scripts/omega_expert_tool.py read-order --profile quick
python3 scripts/omega_expert_tool.py read-order --profile full
python3 scripts/omega_expert_tool.py module-map
python3 scripts/omega_expert_tool.py chat-trace
python3 scripts/omega_expert_tool.py all --json
```

Make shortcut:

```bash
make expert-guide
```

Notes:

- File references are resolved dynamically from source markers, so line numbers stay useful as files move.
- The tool is intentionally read-only and standard-library only.
- It is meant as an operator/developer orientation aid, not a runtime dependency.
