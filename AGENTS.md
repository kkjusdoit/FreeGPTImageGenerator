# Workspace Rules

- For version upgrade tasks, default to a full upstream code update.
- Preserve only active local configuration and runtime data, especially files under `data/` such as `data/config.yaml` and `data/data.db`.
- Do not preserve local feature customizations or code-level behavior changes unless the user explicitly asks for them.
- After completing a version update, restart the current service process so the new code takes effect immediately.
