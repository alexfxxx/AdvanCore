# Decoupled Local Console

## Status

TASK-126 additive scaffold. The Streamlit application remains the supported
operational interface while this console is evaluated.

## Boundary

```text
Browser HTML/CSS/JavaScript
        |
        | read requests or explicit Owner Goal text
        v
FastAPI loopback presentation adapter
        |
        | existing application services / dry-run goal generation
        v
AdvanCore controller and agent_runner authority boundaries
```

The browser is an untrusted presentation client. It has no database session,
shell access, worker adapter, controller decision, task lifecycle, Git
publication or deployment capability.

## Initial endpoints

- `GET /api/status` returns bounded readiness booleans and states. It never
  returns environment values, connection strings or credentials.
- `GET /api/projects` reads through `ProjectService` and `ProjectRepository`.
- `GET /api/knowledge` reads through `KnowledgeService` and
  `KnowledgeItemRepository`.
- `POST /api/owner-goals/preview` invokes existing goal-to-task generation with
  `DryRunWorkerAdapter` and `execute=False`. It launches no planner and writes no
  task file.
- `WS /ws/transcription` reports that voice is disabled and accepts no audio.

Database reads use a rollback-only session. No API route is authorised to
commit a transaction.

## Presentation customization

Colours, spacing, buttons and animations are isolated in `frontend/styles.css`
and use CSS custom properties as design tokens. Page interaction remains in
separate vanilla-JavaScript files. Future owner-selectable themes or animation
preferences can therefore change presentation without altering PostgreSQL,
business services, controller policy or `agent_runner` authority.

## Local startup

After installing the pinned project requirements in an isolated environment:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Binding to `0.0.0.0` is outside TASK-126.

The static frontend is served by FastAPI on the same origin. Explicit CORS
origins exist only for bounded loopback development ports; wildcard origins
are not used.

## Voice-provider future boundary

The browser `MediaRecorder` hook is disabled and discards chunks in memory.
`MediaRecorder` commonly emits compressed browser formats, while Gemini Live
Transcription requires raw 16-bit PCM audio. A later governed task should use
an `AudioWorklet` or controlled server conversion, plus a replaceable
transcription-provider interface.

No provider credential may be embedded in JavaScript. If a browser connects
directly to a provider, the backend must issue a constrained short-lived token.
No audio or transcript is stored by default. A final transcript remains
editable and requires explicit owner submission before it enters the
controller workflow.

## Deliberately absent capabilities

- Task artifact creation or lifecycle approval
- Worker execution or fallback routing
- Database writes or migrations
- Commit, push, PR, merge or deployment
- Gemini connection, credential handling or billing
- Remote access or authentication

Each requires a separate governed task and owner decision.
