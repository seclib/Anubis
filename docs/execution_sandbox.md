# Execution Sandbox

The sandbox is capability based. A task declares required capabilities and the
permission engine checks the selected agent before execution. Denials are
structured events, not silent failures.

Default profile:

- restricted mode
- scratch filesystem
- denied network
- bounded timeout and memory metadata

Production additions:

- all plugin and task execution must pass through sandbox guard;
- host filesystem access is denied;
- raw network access is denied;
- source modification is denied;
- direct OS command execution is denied;
- repeated denials and escape attempts feed the kill switch.

See `config/sandbox.yaml` and `config/production_hardening.yaml`.
