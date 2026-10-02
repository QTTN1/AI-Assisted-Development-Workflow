# DashBite — Containerized Late-Order Prediction Pipeline

**Assignment option:** Option 1 — Extend and Containerize DashBite
**Based on:** [Kedar-V/TestingAndContainerisationDemo](https://github.com/Kedar-V/TestingAndContainerisationDemo) (class demo).

## Purpose

DashBite predicts whether a food-delivery order will be **late**. It runs as five independent stages that only communicate through files in a shared data folder:

| Stage      | Module                  | What it does                                                                                |
| ---------- | ----------------------- | ------------------------------------------------------------------------------------------- |
| Simulator  | `pipeline.simulator`  | Writes a batch of 50 orders every 15 s to`raw/` (some batches are deliberately corrupted) |
| Preprocess | `pipeline.preprocess` | Drops bad rows, adds features →`features/`, logs field failures → `quality/`          |
| Train      | `pipeline.train`      | Retrains after every 2,000 new labeled rows →`models/checkpoint_*.joblib`                |
| Infer      | `pipeline.infer`      | Scores new rows with the newest checkpoint →`predictions/`                               |
| Dashboard  | `pipeline.dashboard`  | Streamlit "Model Pulse" at http://localhost:8501                                            |

The original only ran on macOS/Linux (the Makefile uses `.venv/bin` paths and a bash background script). I'm on Windows, so the goal was to make the whole pipeline run with one Docker command on any OS, and to make it behave well as a container.

## What I changed

- **Dockerfile + `.dockerignore`:** one shared `python:3.12-slim` image for all stages.
- **`compose.yaml`:** one service per stage, all sharing one named volume.
- **Container-readiness improvements:**
  - **Configurable data path:** `DATA_ROOT` env var instead of the hardcoded `<project>/data`.
  - **Persistent storage:** a named volume (`dashbite-data`) keeps data and models across `docker compose down`.
  - **Dashboard health check** against Streamlit's `/_stcore/health` endpoint.
  - **Bounded restarts:** `restart: on-failure:3`, so a crashed stage retries 3 times and then stays stopped for me to inspect instead of looping forever.
  - **Unbuffered logs:** `PYTHONUNBUFFERED=1`, so `docker compose logs` shows progress live.
  - **Containerized tests:** a `test` service runs pytest inside the image.
  - **`.env` overrides** for all pipeline settings.
- The local `make run/status/stop` workflow still works for macOS/Linux users.

## Install and run (Docker)

Requirements: Docker Desktop (or Docker Engine + Compose plugin). Commands are for bash (Git Bash on Windows works).

```bash
git clone https://github.com/QTTN1/AI-Assisted-Development-Workflow.git
cd AI-Assisted-Development-Workflow

docker compose up --build -d      # build the image and start all 5 stages
docker compose ps                 # all services "Up", dashboard "(healthy)"
docker compose logs -f simulator preprocess train infer   # Ctrl+C to stop following
# open http://localhost:8501
docker compose down               # stop (data volume is kept)
docker compose down --volumes     # stop AND delete all pipeline data
```

**Note:** the first model and predictions appear after about **10 minutes**. Training waits for 2,000 rows (50 rows every 15 s). That's DashBite's default behavior. Lower it with `TRAIN_EVERY_N_EVENTS` in `.env` if you want faster results.

If a stage stops after its 3 restart attempts, check and restart it manually:

```bash
docker compose logs --tail 50 <service>
docker compose restart <service>
```

### Configuration

Create a `.env` file in the project root to override defaults (it's gitignored):

```bash
echo "CORRUPT_BATCH_RATE=1.0" > .env                                 # bash
# PowerShell: Set-Content .env 'CORRUPT_BATCH_RATE=1.0'
docker compose up -d --force-recreate
docker compose exec simulator printenv CORRUPT_BATCH_RATE         # confirm it applied
```

| Variable                  | Default       | Meaning                                   |
| ------------------------- | ------------- | ----------------------------------------- |
| `TRAIN_EVERY_N_EVENTS`  | `2000`      | Retrain after this many new labeled rows  |
| `BATCH_SIZE`            | `50`        | Orders per simulator batch                |
| `POLL_INTERVAL_SECONDS` | `15`        | Seconds between batches/polls             |
| `CORRUPT_BATCH_RATE`    | `0.25`      | Fraction of batches that contain bad rows |
| `RANDOM_SEED`           | `42`        | Training seed                             |
| `DATA_ROOT`             | `/app/data` | Data folder inside the containers         |

**Reading the drop rate:** a corrupted batch drops 15 of its 50 rows (30%), and a clean batch drops 0%. The dashboard's **Drop rate** is a running average over *all* batches in the volume, so after changing `CORRUPT_BATCH_RATE` it moves gradually instead of jumping. Per-batch numbers are in `docker compose logs preprocess`.

## Testing

```bash
docker compose run --build --rm test      # full pytest suite inside the container
```

Locally (any OS, Python 3.12):

```bash
pip install -r requirements.txt
python -m pytest                           # unit + regression + integration
```

Local background runner (macOS/Linux only): `make install`, `make run`, `make status`, `make stop`.

## Manual smoke test

Run by me on Windows 11 (Git Bash/PowerShell, Docker Desktop).

**First run (after the Builder stage):**

| Check                            | Result                                                                                                                             |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `docker compose up --build -d` | ✅ image built, 5 containers started, volume created                                                                               |
| `docker compose ps`            | ⚠️ all 5 "Up", but no health status shown for the dashboard                                                                    |
| Stage logs                       | ❌`docker compose logs` printed nothing for simulator/train/infer                                                                |
| Dashboard                        | ⚠️ loaded and showed order volume (1,600 samples), but**drop rate and field failures stayed at 0%** and no predictions yet |
| Restart (`down` → `up -d`)  | ✅ restarted cleanly, volume kept                                                                                                  |
| Local`python -m pytest`        | ✅ 32 passed                                                                                                                       |

I sent these problems to the Tester -->

**Final run (after the Tester fixes):**

| Check              | Result                                                                                                                                         |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Build + start      | ✅ all 5 services up                                                                                                                           |
| Dashboard          | ✅ drop rate ~30% on corrupted batches, late-flag rate ~52–53%, field-failures chart populated (prep_minutes and distance_km most common)     |
| Predictions        | ✅ appeared once training passed 2,000 rows                                                                                                    |
| Logs               | ✅ preprocess prints per-batch lines, e.g.`35/50 rows kept, drop_rate=30.0%`                                                                 |
| Corruption setting | ✅`CORRUPT_BATCH_RATE=1.0` in `.env` → `printenv` showed `1.0`, every batch dropped 15/50 rows, dashboard drop rate climbed 9% → 10% |
| Health check       | ✅ dashboard shows`(healthy)`                                                                                                                |
| Tests              | ✅ all tests passed                                                                                                                           |


## How each AI role contributed

All three roles used GitHub Copilot in VS Code, each in a fresh chat. Transcripts are in `docs/transcripts/`.

- **Architect:** read the repo and found that `paths.py` and the dashboard hardcode the data folder. It then gave me options for storage, restart behavior and health checks instead of deciding for me. I asked for an alternative a named volume, `on-failure:3` restarts and health checks, and it wrote the plan to `docs/plan.md`.
- **Builder:** wrote the Dockerfile, `compose.yaml`, `.dockerignore`, the `DATA_ROOT` config change, tests and the Docker README section. It also did the work in a separate git worktree, so I had to have it move the changes into `main`.
- **Tester:** compared the build against `docs/plan.md` and found that the Builder had deleted the data-corruption feature and its tests, along with the Makefile background runner. That explained my 0% drop rate. It also confirmed the missing health check and empty logs. With my priorities, it restored the corruption path and tests, restored the local runner, added the health check and unbuffered logs, and explained how the drop rate is calculated.

## AI recommendations I accepted

- **Named Docker volume** instead of bind-mounting `data/`. It avoids Windows path and permission problems.
- **Dashboard health check against Streamlit's health endpoint** and **`PYTHONUNBUFFERED=1`**, both from the Tester.
- **Not restoring the prompt-board / static-site files.** The Tester pointed out those were the actual teaching material, unlike the corruption feature.

## Recommendations I changed or rejected

- **Restart policy:** the Architect recommended `restart: unless-stopped`. I rejected it because a real bug would restart forever, and changed it to `on-failure:3` so failures stop and I can check the logs. The Builder still shipped `unless-stopped`, so I corrected `compose.yaml` myself.
- **Classroom framing:** the Builder built everything as a teaching demo. I told it to refocus on a working containerized app. It then over-deleted and removed the corruption feature, which I had the tester restore.
- **The ~10-minute delay before predictions:** the Tester flagged it, but I chose not to change it. It's DashBite's default training threshold, so I documented it instead of changing pipeline behavior.
- **Health checks on all five services:** I originally chose this in the Architect stage. In the end only the dashboard has one, because the other stages are loop processes with no endpoint to probe, and checking them through `docker compose ps` and the logs was enough. *(Known deviation from the plan.)*

## How I verified the final result

- Ran the full test suite myself, locally and in the container.
- Rebuilt from a fresh volume (`docker compose down --volumes`, then `up --build -d`) and watched the dashboard until predictions and field failures appeared.
- Read the preprocess logs to confirm each batch was either clean or corrupted, about 1 in 4 batches at the default rate.
- Tested the `.env` override. My first attempt silently didn't apply because the `.env` file wasn't in the project folder. I caught it by checking `printenv CORRUPT_BATCH_RATE` inside the container and fixed it, then confirmed the dashboard drop rate moved as expected.
- Checked `git status` and after each AI stage, which is how I caught the Builder's deleted files and the plan that was left on a side branch.

## Repository layout

```
compose.yaml, Dockerfile, .dockerignore
pipeline/        stage code (config, paths, simulator, preprocess, train, infer, dashboard)
tests/           unit / regression / integration
scripts/         local background runner (macOS/Linux)
docs/plan.md     Architect plan
docs/transcripts/ttn21_architect.txt, ttn21_builder.txt, ttn21_tester.txt
```
