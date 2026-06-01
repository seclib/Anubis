# Secure Tool Execution Sandbox

## Architecture

```text
USER / LLM
  |
  v
SecureToolExecutionRequest
  |
  v
ToolSchemaValidator
  - rejects unknown tools
  - rejects unknown parameters
  - enforces per-tool JSON schema
  |
  v
PermissionRegistry
  - deny by default
  - no shell permission
  - path containment checks
  |
  v
ContainerBoundarySandboxExecutor
  - no shell
  - no eval/exec
  - timeout enforced
  - runs inside read-only tool-runner container
  |
  v
OutputSanitizer
  - strips sensitive keys
  - removes host metadata
  - truncates large output
  |
  v
ImmutableAuditLogger
  - append-only JSONL
  - hash chained events
  - persisted on tool_audit volume
```

## Tool Permissions

```json
{
  "web.search": {
    "network": true,
    "filesystem": false,
    "shell": false
  },
  "file.read": {
    "network": false,
    "filesystem": "read_only",
    "shell": false,
    "allowed_paths": ["/workspace/sandbox"]
  },
  "note.write": {
    "network": false,
    "filesystem": "read_write",
    "shell": false,
    "allowed_paths": ["/workspace/sandbox"]
  },
  "memory.retrieve": {
    "network": false,
    "filesystem": false,
    "shell": false
  }
}
```

## Secure Request

```json
{
  "tool_name": "file_read",
  "parameters": {
    "relative_path": "notes/example.md",
    "max_bytes": 12000
  },
  "request_id": "req_123"
}
```

## Secure Error

```json
{
  "error": true,
  "code": "PATH_DENIED",
  "message": "Requested path escapes the sandbox workspace",
  "request_id": "req_123"
}
```

## Attack Scenarios

```text
Prompt injection requests shell:
  Mitigation: no shell permission exists; executor has no shell path.

Path traversal reads /etc/passwd:
  Mitigation: PermissionRegistry resolves paths and denies escapes.

Unknown tool name:
  Mitigation: ToolSchemaValidator rejects before execution.

Oversized tool output:
  Mitigation: OutputSanitizer truncates before returning to agent.

Secret leakage in output:
  Mitigation: sensitive keys are redacted recursively.

Audit tampering:
  Mitigation: JSONL events are hash chained and stored on a dedicated volume.

Container breakout blast radius:
  Mitigation: compose uses read_only, no-new-privileges, cap_drop ALL, tmpfs /tmp, non-root user.
```
