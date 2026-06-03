# ANUBIS Optimized Docker Builds

The optimized production layout uses multi-stage Dockerfiles and split
dependency sets so runtime images do not contain compilers, pip caches,
Node dependencies, Rust build artifacts, or local-model CUDA stacks.

## Images

- `anubis-api:optimized`: API/runtime image using `requirements/prod.txt`.
- `anubis-core:optimized`: orchestration/core service using `requirements/core.txt`.
- `anubis-ml:optimized`: lightweight ML/vector service using `requirements/ml.txt`.
- `anubis-tooling:optimized`: git/shell/filesystem tooling worker using `requirements/tooling.txt`.

Local transformer models are intentionally excluded from the default ML image.
Build a local-model image only when required:

```bash
docker build \
  --target runtime \
  -f infra/docker/Dockerfile.ml \
  --build-arg ML_REQUIREMENTS=requirements/ml-local-models.txt \
  -t anubis-ml:local-models \
  .
```

## Build

```bash
bash infra/scripts/build-optimized-images.sh
```

Or with Compose:

```bash
docker compose -f infra/docker/docker-compose.optimized.yml build
docker compose -f infra/docker/docker-compose.optimized.yml up -d
```

## Runtime Rules

Runtime images must not include:

- `.venv/`
- `node_modules/`
- `desktop-ui/node_modules/`
- `runtime-tauri/target/`
- `src-tauri/target/`
- `dist/`
- `desktop-ui/dist/`
- pip caches
- cargo caches
- compilers/build-essential

Runtime images may include:

- Python runtime
- installed wheels only
- source modules required by the service role
- `git` only in API/tooling images that need repository operations
- `tini` for signal handling

## Expected Size Reduction

The previous all-in-one image installed `requirements.txt`, which included
`sentence-transformers`, `torch`, `triton`, `nvidia-*`, `cuda-*`, and
`chromadb`. Those packages account for most of the 20GB+ image size.

Default optimized images install `requirements/prod.txt`, which excludes local
model dependencies. The heavyweight model stack moves to an optional dedicated
ML image.
