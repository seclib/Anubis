# ANUBIS plugins

Plugins are local modules described by JSON manifests. The desktop runtime loads
manifests from this directory and from `skills/*.plugin.json`.

The MVP contract is intentionally small:

- `name`: stable local plugin id
- `display_name`: human-readable label
- `description`: short command palette summary
- `enabled`: local toggle state
- `triggers`: phrases used by the agent/router
- `skills`: local skill or module paths owned by the plugin

Plugins should not import UI code. Runtime services discover manifests and pass
context into the agent layer.
