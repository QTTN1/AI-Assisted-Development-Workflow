# DashBite — living plan

Classroom handoff for Architect → Implementer → Reviewer. Stages are appended below; do not wholesale-overwrite earlier sections.

## Wrap-up — Run the full stack

### Goal
Run simulator, preprocess, train, infer, and Model Pulse as durable background jobs via the Makefile.

### Architecture / boundaries
- Public interface: `make run`, `make status`, `make stop`
- Implementation helper: `scripts/pipeline_bg.sh` (nohup + PID files + log redirection)
- Foreground single stages remain: `make simulator|preprocess|train|infer|dashboard`
- Default poll cadence: `POLL_INTERVAL_SECONDS=15`
- Dashboard: http://localhost:8501 (Model Pulse only)

### Manual Smoke Test

#### What we're proving
The full pipeline stays up in the background, writes through `data/raw` → `data/features` → `data/predictions`, and Model Pulse updates on :8501.

#### Terminal
```bash
make run
make status
# optional live logs:
tail -f .logs/simulator.log .logs/preprocess.log .logs/train.log .logs/infer.log
# or open http://localhost:8501
```

#### Watch for
- `make status` shows UP for simulator, preprocess, train, infer, dashboard
- New files under `data/raw/`, then `data/features/`, then `data/predictions/`
- Model Pulse at http://localhost:8501 (volume / scores / failures)
- Logs under `.logs/`; PIDs under `.logs/pids/`

#### Stop
```bash
make stop
make status   # expect DOWN
```

## Docker — One-command local stack

### Goal and requirements
- Run the simulator, preprocess, train, infer, and Streamlit dashboard as five separate Compose services from one shared image.
- Start the whole stack with one Windows-friendly command: `docker compose up --build`.
- Preserve the file-based stage boundaries: services exchange data only through the shared `data/` directory, not through APIs or in-memory coupling.
- Keep the existing local Makefile workflow and pipeline/ML behavior unchanged. The only application change is allowing container services to select a shared data root.
- Persist shared files through a named Docker volume across container rebuilds and ordinary `docker compose down` / `up` cycles.
- Limit automatic recovery to `restart: "on-failure:3"`; after retries are exhausted, inspect the failed service and restart it manually.
- Give all five services health checks, while documenting the limits of liveness checks for polling workers.
- Keep the implementation small enough for a few hours and compatible with Docker Desktop on Windows.

### Proposed architecture and decisions
- Build one `dashbite:local` image from one Dockerfile and use it for five services:
  - `simulator`: `python -m pipeline.simulator`
  - `preprocess`: `python -m pipeline.preprocess`
  - `train`: `python -m pipeline.train`
  - `infer`: `python -m pipeline.infer`
  - `dashboard`: Streamlit bound to `0.0.0.0:8501`, published as host port `8501`
- Mount one named volume at the same container data root in every service. Use a `DATA_ROOT` setting to resolve each pipeline folder beneath that mount. A named volume is easier to use consistently on Windows than a host bind mount, but its contents are less directly browsable.
- Set the same restart policy on each service: `on-failure:3`. This recovers from a transient crash without a permanent restart loop. After the third retry, use Compose status and logs, then manually restart the service.
- Define health checks per service. The dashboard check should request Streamlit's local health endpoint. Worker checks should verify that their expected stage process is alive; they must not require upstream files because empty or not-yet-created input is normal at startup. Do not use health status to gate service startup: the stages poll shared files and tolerate starting before upstream output exists.
- Run `docker compose up --build` in the foreground for the one-command path and immediate combined logs. Users can stop the stack with Ctrl+C; detached operation may be documented as an optional variant.
- Avoid scaling any service in this initial Compose setup. The file handoffs and checkpoint/state writers are not designed to coordinate concurrent replicas.

### Proposed changes and files

| File | Change |
|------|--------|
| `Dockerfile` | Create a single Python 3.12 slim image; install the existing `requirements.txt`; copy the pipeline package; use an exec-form stage command that Compose can override. |
| `docker-compose.yml` | Create five services from the same built image, shared environment settings, named `dashbite-data` volume, restart policy, per-service health checks, and dashboard port mapping. |
| `.dockerignore` | Create build-context exclusions for `.git`, `.venv`, tests, generated data, logs, Python caches, and other local-only files. |
| `pipeline/paths.py` | Support `DATA_ROOT` when no explicit test/base directory is supplied; preserve the current `<base>/data` behavior for tests and local callers that pass a base. Fall back to `<project>/data` when the variable is unset. |
| `pipeline/dashboard/app.py` | Stop forcing `PROJECT_ROOT` as the dashboard data base so dashboard reads use the same `DATA_ROOT` behavior as the worker stages; preserve the local default. |
| `README.md` | Add a clear Docker section with prerequisites, one-command startup, dashboard URL, status/log commands, manual restart procedure, stop/persistence behavior, and volume deletion warning. Retain the current local setup and Makefile instructions. |
| `docs/plan.md` | Append this implementation handoff without replacing earlier living-plan content. |

No ML modules, feature logic, model behavior, local Make targets, or dependency versions should otherwise change. Keep the existing settings' behavior locally; Compose may specify demo-friendly environment values without changing application defaults.

### README Docker section to add

The eventual README section should include, at minimum:

```powershell
# From the repository root; starts all five services and streams their logs
docker compose up --build
```

- Open `http://localhost:8501` for Model Pulse.
- Check service state with `docker compose ps`.
- Follow all logs with `docker compose logs -f`; follow one service with `docker compose logs -f preprocess` (substitute any service name).
- Manually recover a failed service with `docker compose restart preprocess`; if it was removed/stopped as part of teardown, use `docker compose up -d preprocess`.
- Stop the foreground stack with Ctrl+C, or use `docker compose down` from another terminal. The named data volume remains.
- Warn that `docker compose down -v` deletes the named volume and all generated pipeline data.
- State the Docker Desktop / Docker Compose v2 prerequisite and that a named volume keeps data inside Docker rather than displaying it under the repository's host `data/` folder.

### Container-behavior options selected

| Concern | Selected design | Trade-off / concern |
|---------|-----------------|---------------------|
| Shared state on Windows | Persistent named volume | Reliable cross-service mount without host path syntax issues; less convenient for browsing or editing CSVs directly from the host. |
| Crash recovery | `on-failure:3`, then manual restart | Handles temporary process failures and bounds retries; a failing service will remain stopped after its retries, so users must check logs and restart it. |
| Health visibility | Health checks for all five services | Provides Compose health state beyond a running/stopped status. Worker liveness does not prove that new data is flowing, and an endpoint/process probe can be green while the broader pipeline is stalled. |

### Risks and design concerns
- `DATA_ROOT` must mean the directory containing `raw/`, `features/`, `models/`, `predictions/`, and `quality/`; it must not accidentally become `<configured-root>/data`. Explicit-base tests and the unchanged local default must continue to resolve exactly as before.
- The dashboard currently passes `PROJECT_ROOT` directly to its readers; missing that override would make the dashboard appear empty even as the container workers write to the shared volume.
- The simulator and other workers are long-running poll loops. Compose health checks can establish process liveness (and dashboard availability), but must not claim end-to-end processing readiness. Avoid health-based startup dependencies that prevent otherwise-tolerant workers from starting.
- The shared volume outlives the containers. Users may mistake retained data for a fresh run; make the destructive `down -v` behavior explicit and never use it as the normal stop command.
- Multiple preprocess/train/infer replicas can race on markers, model state, or predictions. Keep one replica per service and do not present scaling as supported.
- Ensure the dashboard binds to `0.0.0.0`; binding only to container localhost would make port 8501 inaccessible from Windows.
- Use a Linux container path such as `/app/data` inside Compose; do not embed Windows host paths in the Compose volume declaration.
- A slim Python image reduces image size, but scientific Python wheels may increase build time. Pinning dependency versions or changing the dependency set is out of scope unless image build testing reveals a concrete compatibility issue.
- The selected retry policy covers process exit failures, not a worker stuck indefinitely. Health checks report unhealthy state but Compose does not automatically restart a process solely because it is unhealthy.

### Testing and verification
1. Run the pre-change baseline and post-change full suite from the existing local environment: `pytest`. Keep unit, regression, and integration tests passing without Docker.
2. Add focused path tests for an explicit `DATA_ROOT`, the unset-variable project default, and explicit test/base paths. Verify all five path helpers and directory creation use the intended root.
3. Validate the Compose file is rendered as intended with `docker compose config`; confirm there are exactly five stage services, all use the same image/build, all mount the same named volume, and each has the bounded restart and health-check configuration.
4. Build and launch with the documented one-command workflow: `docker compose up --build`. Confirm all services become healthy and the dashboard responds at `http://localhost:8501`.
5. Observe the shared data flow: raw CSVs appear, preprocess writes features and quality metrics, training writes a checkpoint once its threshold is reached, inference writes predictions, and the dashboard reads from that same volume.
6. Confirm `docker compose ps` exposes useful service/health state and `docker compose logs -f <service>` works for each service.
7. Exercise manual restart on a worker with `docker compose restart <service>` and confirm it returns to healthy operation without losing named-volume data. Confirm `docker compose down` retains data for the next start.
8. Review the README's Windows commands and dashboard URL against the verified Compose configuration. Do not run `docker compose down -v` in routine verification; volume deletion is a documented user-directed cleanup only.
