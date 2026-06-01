# Anubis Minimal Kernel

```text
User
  -> FastAPI /v1/agent/run
  -> Agent loop
  -> Tool dispatcher optional
  -> Function sandbox
  -> Memory decision
  -> Response
```

```bash
cd anubis/kernel
pip install -e .
uvicorn anubis_kernel.main:create_app --factory --reload --port 8000
```

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/v1/agent/run \
  -H 'content-type: application/json' \
  -d '{"input":"search memory architecture"}'
```
