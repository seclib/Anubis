# Frontend

The frontend is the Tauri/React dashboard for Anubis Desktop OS.

## Entry Points

- React app: `desktop/src/main.tsx`
- API client: `desktop/src/api.ts`
- Styles: `desktop/src/styles.css`
- Native shell: `desktop/src-tauri/`

## Interface

The frontend talks to:

- Tauri launcher commands for service lifecycle and logs.
- Local FastAPI routes at `http://127.0.0.1:8000`.

## Coupling Rule

Frontend code must not import Python modules or assume direct filesystem access.
All backend behavior goes through HTTP or Tauri commands.
