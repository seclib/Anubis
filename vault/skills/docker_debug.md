# skill: docker_debug

tags: [skill, devops]

## when to use
Use when Docker containers fail, restart unexpectedly, cannot connect to services, or behave differently from local execution.

## steps
1. Check service status and recent logs.
2. Inspect environment variables, ports, volumes, and networks.
3. Restart only the affected service when the cause is isolated.
4. Re-run the failing command and record the durable fix.

## tools
Use read_note for existing runbooks, search_rag for prior failures, and write_note for the final reusable fix.
