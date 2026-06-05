# Security Model

ANUBIS follows least authority:

- agents receive explicit capability grants;
- execution is sandbox-authorized before task handlers run;
- sensitive memory is rejected unless encrypted or externally referenced;
- evolution mode is disabled by default;
- self-modification is simulation-first and policy-gated;
- critical modules such as bootstrap, orchestrator, and cognitive loop are protected.

Production hardening is defined in `docs/production_hardening.md` and the
machine-readable policies under `config/`.

Required production controls:

- deny-by-default permissions;
- no wildcard grants;
- no direct OS execution;
- no runtime code injection;
- no source modification;
- plugin execution through sandbox guard only;
- append-only audit logging with integrity checks;
- kill switch activation for critical sandbox escape attempts.
