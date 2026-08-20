# Participant Run-Through Guide — Deploying the Northstar LLM Agent

Panduan ini membawa Anda dari source code agent sampai public deployment yang dapat diuji dan dipulihkan. Ikuti langkah secara berurutan karena evidence dari satu tahap akan dipakai pada tahap berikutnya.

> **Peringatan biaya:** Project ini tidak memiliki mock, offline, atau deterministic provider. Setiap agent run dan live test memanggil external model API menggunakan `API_KEY`. Render Free dapat digunakan untuk hosting kelas, tetapi penggunaan model API tetap berbayar.

> **Security rule:** Jangan memasukkan API key ke source code, Git, Docker image, command screenshot, browser, atau laporan tugas. Gunakan `.env` untuk local runtime dan secret environment variables di Render.

## Hasil Akhir

Pada akhir hands-on, Anda akan memiliki:

- FastAPI service dengan asynchronous agent run
- Swagger API dan customer-support UI
- Sanitized tool activity, citations, token usage, latency, dan cost estimate
- Docker image `linux/amd64` di public registry
- Public Render service
- Evidence dari successful release, failed release, dan recovery

## Estimasi Waktu

| Bagian | Durasi |
|---|---:|
| Inspect dan setup | 20 menit |
| Live tests dan local API | 30 menit |
| UI dan Swagger verification | 20 menit |
| Docker build dan container test | 30 menit |
| Registry dan Render deployment | 30–45 menit |
| Failure dan recovery exercise | 20 menit |

Cold start, image upload, model latency, atau rate limit dapat menambah waktu.

## Prerequisites

Pastikan Anda memiliki:

- Python 3.11 atau lebih baru
- Git repository bootcamp ini
- Docker Desktop atau Docker Engine yang sedang berjalan
- Valid `API_KEY`
- Model identifier yang mendukung Responses API function calling
- Internet access
- Public container registry account, misalnya Docker Hub
- Render account

Instructor harus sudah mengonfirmasi model access, quota, rate limit, dan budget kelas.

## System yang Akan Dibangun

```text
Browser UI / Swagger
        |
        v
FastAPI run service
        |
        v
Northstar agent loop ----> Responses-compatible model API
        |
        +----> policy search
        +----> owned-order lookup
        +----> scoped ticket creation
        +----> human escalation
        |
        v
Sanitized events + SQLite telemetry
```

FastAPI menyediakan endpoint berikut:

```text
POST /v1/runs
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/cancel
GET  /health/live
GET  /health/ready
GET  /version
GET  /docs
```

---

## Step 1 — Inspect Agent dan Deployment Boundary

### Tujuan

Mengenali responsibility agent, tool, serving layer, UI, dan container sebelum menjalankan system.

### Masuk ke project

Dari repository root, jalankan salah satu command berikut.

PowerShell:

```powershell
Set-Location modules\12-model-serving-production-grade-deployment\v2\project
Get-ChildItem
```

macOS/Linux:

```bash
cd modules/12-model-serving-production-grade-deployment/v2/project
find app src data scripts tests -maxdepth 2 -type f
```

### Inspect file utama

| Path | Responsibility |
|---|---|
| `src/agent.py` | Responses API function-calling loop dan three-tool-call limit |
| `src/tools.py` | Tool schema, ownership checks, dan ticket permission |
| `src/setup_lab.py` | Synthetic Northstar data initialization |
| `app/service.py` | Run states, background execution, events, dan cancellation |
| `app/main.py` | FastAPI endpoint, readiness, version, dan UI serving |
| `app/static/` | Browser UI tanpa model credential |
| `tests/` | Bounded live model scenarios |
| `Dockerfile` | Non-root immutable runtime image |

> **Checkpoint 1:** Anda dapat menjelaskan mengapa browser memanggil FastAPI, bukan model provider secara langsung.

---

## Step 2 — Buat Environment dan Configure Live Model

### Tujuan

Menginstal dependency dan menyediakan credential hanya melalui runtime environment.

### Buat virtual environment

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

### Edit `.env`

Isi value yang diberikan instructor:

```dotenv
API_KEY=<instructor-provided-key>
AGENT_MODEL=<responses-function-calling-model>
API_BASE_URL=
INPUT_COST_PER_1M=0
OUTPUT_COST_PER_1M=0
APP_VERSION=module12-v2-local
FORCE_READINESS_FAILURE=0
```

`API_BASE_URL` boleh kosong. Isi hanya jika instructor menyediakan endpoint yang mendukung Responses API beserta function-calling wire format yang kompatibel.

Rate cost bersifat opsional dan hanya dipakai untuk estimated cost. Gunakan rate yang telah diverifikasi instructor; jangan menebak pricing.

### Verify configuration tanpa menampilkan key

```bash
python -c "from src.config import load_model_settings; print(load_model_settings().agent_model)"
```

**Expected result:** Hanya model identifier yang tercetak.

> **Checkpoint 2:** `.env` ada secara local, tidak ter-track Git, dan terminal tidak pernah mencetak API key.

### Troubleshooting

| Problem | Resolution |
|---|---|
| `python` tidak ditemukan | Install Python 3.11+ atau gunakan launcher yang disediakan instructor |
| PowerShell memblokir activation | Ikuti execution-policy guidance dari instructor atau gunakan Command Prompt |
| `ModuleNotFoundError` | Pastikan `.venv` aktif lalu ulangi dependency installation |
| Missing `API_KEY` atau `AGENT_MODEL` | Periksa nama variable di `.env`; tidak ada fallback runtime |

---

## Step 3 — Initialize Northstar Data dan Jalankan Live Tests

### Tujuan

Membuktikan policy retrieval, ownership, ticket permission, dan FastAPI lifecycle menggunakan live model.

### Initialize data

```bash
python -m src.setup_lab --reset
```

Representative setup output:

```text
Application database: .../data/customer_service.db
Telemetry database: .../data/telemetry.db
Northstar healthy and stale knowledge-base versions are ready.
```

### Jalankan bounded live suite

```bash
pytest -m live -q
```

Suite menjalankan empat live scenarios:

1. Current policy retrieval
2. Blocked cross-customer order lookup
3. Scoped support-ticket creation
4. FastAPI request lifecycle

Assertions memeriksa tool selection, authorization, citations, final state, dan response structure. Exact model wording dapat berbeda.

**Expected result:** Empat test lulus. Token usage, latency, dan estimated cost dapat berbeda antar model atau provider.

> **Checkpoint 3:** Cross-customer test menghasilkan `authorization_failed`, ticket test menghasilkan `ticket_created=true`, dan jumlah tool call tidak melebihi tiga.

### Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Test langsung gagal pada configuration | Required variable belum tersedia | Perbaiki `.env` sebelum retry |
| `401` atau `403` | Key invalid atau model tidak diizinkan | Hubungi instructor |
| Rate-limit error | Class quota atau request rate terlampaui | Jangan melakukan uncontrolled retry; koordinasikan dengan instructor |
| Expected tool tidak dipanggil | Model/endpoint tidak memenuhi function-calling contract | Verifikasi `AGENT_MODEL` dan `API_BASE_URL` |
| Wording berbeda tetapi evidence benar | Normal model variability | Nilai evidence dan state, bukan exact prose |

---

## Step 4 — Start FastAPI dan Inspect Health

### Tujuan

Menjalankan local API dan membedakan liveness, readiness, serta paid live smoke test.

### Start server

```bash
uvicorn app.main:app --reload
```

Biarkan terminal ini tetap berjalan. Buka URL berikut:

- UI: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`
- Liveness: `http://127.0.0.1:8000/health/live`
- Readiness: `http://127.0.0.1:8000/health/ready`
- Version: `http://127.0.0.1:8000/version`

Representative readiness structure:

```json
{
  "ready": true,
  "status": "ready",
  "model": "<configured-model>",
  "version": "module12-v2-local",
  "reasons": [],
  "provider_probe": "not_called"
}
```

`/health/ready` tidak memanggil model sehingga platform health checks tidak membuat token cost.

> **Checkpoint 4:** Liveness dan readiness mengembalikan HTTP `200`, version benar, dan `provider_probe` bernilai `not_called`.

### Troubleshooting

- `503`: baca bounded `reasons` pada response. Periksa configuration dan local database.
- Port 8000 dipakai: jalankan `uvicorn app.main:app --reload --port 8001`.
- Import error: pastikan command dijalankan dari folder `v2/project` dengan `.venv` aktif.

---

## Step 5 — Jalankan Real Agent Run melalui Swagger

### Tujuan

Menguji public API contract tanpa bergantung pada UI.

1. Buka `http://127.0.0.1:8000/docs`.
2. Expand `POST /v1/runs`.
3. Klik **Try it out**.
4. Gunakan payload berikut:

```json
{
  "message": "What is the current return window? Search policy first.",
  "category": "returns",
  "authenticated": false,
  "allow_ticket_creation": false,
  "expected_document_ids": ["KB-RET-001"]
}
```

5. Klik **Execute**.
6. Pastikan response adalah `202 Accepted`.
7. Copy `run_id` atau `status_url` dari response.
8. Gunakan `GET /v1/runs/{run_id}` sampai state menjadi terminal.
9. Buka `GET /v1/runs/{run_id}/events` untuk melihat sanitized events.

Representative accepted response:

```json
{
  "run_id": "<generated-run-id>",
  "status": "queued",
  "status_url": "/v1/runs/<generated-run-id>",
  "events_url": "/v1/runs/<generated-run-id>/events"
}
```

**Expected result:** State akhirnya `completed`, `tool_calls` berisi `search_knowledge_base`, retrieval evidence berisi `KB-RET-001`, dan final answer memiliki policy citation.

> **Checkpoint 5:** Public response memiliki run ID, status, citations, latency, token usage, dan estimated cost tanpa API key, raw prompt, atau hidden reasoning.

---

## Step 6 — Verify Customer-Support UI

### Tujuan

Memeriksa end-to-end user flow, ownership boundary, scoped permission, dan sanitized tool evidence.

Buka `http://127.0.0.1:8000/`, lalu jalankan tiga scenario berikut.

### Scenario A — Anonymous policy request

- Customer: **Anonymous**
- Category: **Delivery**
- Ticket permission: **Off**
- Message:

```text
How long does standard delivery normally take? Search the policy before answering.
```

Expected evidence: knowledge-base search dan delivery-policy citation.

### Scenario B — Blocked cross-customer lookup

- Customer: **CUST-100 · authenticated**
- Category: **Order status**
- Ticket permission: **Off**
- Message:

```text
Use the order lookup tool for ORD-2002 and tell me its status.
```

`ORD-2002` dimiliki `CUST-200`, sehingga CUST-100 tidak boleh menerima private order data.

Expected evidence: `lookup_order_status`, `authorization_failed`, dan `private_data_disclosed=false`.

### Scenario C — Scoped ticket creation

- Customer: **CUST-100 · authenticated**
- Category: **Damaged item**
- Ticket permission: **On**
- Message:

```text
My delivered item is completely unusable and damaged. Search the policy, then create the appropriate support ticket.
```

Expected evidence: policy retrieval, ticket tool, dan `ticket_created=true`.

Inspect untuk setiap run:

- Run state dan request ID
- Final answer dan citations
- Sanitized tool timeline
- Model dan app version
- Latency dan token usage
- Estimated cost

> **Checkpoint 6:** Hanya Scenario C membuat ticket. Browser tidak menampilkan hidden reasoning, raw customer message dalam tool event, unsanitized tool arguments, atau provider key.

### Cancellation check

Saat sebuah run masih `queued` atau `running`, klik **Cancel run**. Cancellation bersifat cooperative: in-flight provider request mungkin selesai sebelum agent mencapai cancellation boundary berikutnya.

---

## Step 7 — Build `linux/amd64` Docker Image

### Tujuan

Membuat immutable release candidate yang sama untuk local dan cloud deployment.

PowerShell:

```powershell
$env:NORTHSTAR_IMAGE="docker.io/<user>/northstar-agent:module12-v2"
docker build --platform linux/amd64 -t $env:NORTHSTAR_IMAGE .
```

Bash:

```bash
export NORTHSTAR_IMAGE="docker.io/<user>/northstar-agent:module12-v2"
docker build --platform linux/amd64 -t "$NORTHSTAR_IMAGE" .
```

Ganti `<user>` dengan registry namespace Anda.

### Inspect image

PowerShell:

```powershell
docker image inspect $env:NORTHSTAR_IMAGE --format '{{.Os}}/{{.Architecture}} {{.Id}}'
```

Bash:

```bash
docker image inspect "$NORTHSTAR_IMAGE" --format '{{.Os}}/{{.Architecture}} {{.Id}}'
```

**Expected result:** Output dimulai dengan `linux/amd64` dan menampilkan image ID.

> **Checkpoint 7:** Image tidak memiliki `API_KEY`. `.env` hanya akan diberikan saat runtime.

### Troubleshooting

- Pastikan Docker Desktop atau Docker daemon berjalan.
- Jalankan build dari `v2/project`, tempat `Dockerfile` berada.
- Gunakan lowercase image/repository name.
- Pastikan tersedia disk space yang cukup untuk base image dan build layer.

---

## Step 8 — Run Image dengan Runtime Secrets

### Tujuan

Membuktikan container dapat menjalankan system secara independen dari local Python process.

Hentikan Uvicorn local terlebih dahulu agar port 8000 bebas.

PowerShell:

```powershell
docker run --rm -p 8000:8000 --env-file .env -e PORT=8000 $env:NORTHSTAR_IMAGE
```

Bash:

```bash
docker run --rm -p 8000:8000 --env-file .env -e PORT=8000 "$NORTHSTAR_IMAGE"
```

Buka kembali:

- `http://127.0.0.1:8000/health/ready`
- `http://127.0.0.1:8000/version`
- `http://127.0.0.1:8000/`

**Expected result:** Container menjadi ready, melaporkan `module12-v2-local`, dan UI dapat menjalankan real agent request.

> **Checkpoint 8:** System berfungsi dari packaged image, bukan dari Uvicorn local process.

Jika port 8000 masih dipakai:

```bash
docker run --rm -p 8001:8000 --env-file .env -e PORT=8000 <user>/northstar-agent:module12-v2
```

Kemudian buka `http://127.0.0.1:8001`.

---

## Step 9 — Execute Container Smoke Test

### Tujuan

Menghubungkan image identity dengan satu bounded live behavior check.

Buka terminal kedua, aktifkan `.venv`, lalu jalankan:

```bash
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

Smoke test memeriksa:

1. Service ready
2. Run diterima
3. Run mencapai terminal `completed`
4. Policy response grounded

Probe ini membuat satu paid model request.

**Expected result:** Script mencetak completed run snapshot dan selesai dengan exit code `0`.

> **Checkpoint 9:** Simpan image ID, app version, run ID, dan smoke-test output sebagai release evidence. Pastikan output tidak mengandung secret.

Jika terjadi timeout, inspect status endpoint dan container logs sebelum melakukan paid retry:

```bash
docker ps
docker logs <container-id>
```

---

## Step 10 — Publish Exact Image

### Tujuan

Menyimpan verified artifact di registry yang dapat diakses Render.

```bash
docker login
docker push <user>/northstar-agent:module12-v2
docker image inspect <user>/northstar-agent:module12-v2 --format '{{.Id}}'
```

Lakukan login secara interaktif. Jangan menulis password atau token ke Markdown, screenshot, atau shell script.

Setelah push:

1. Buka registry page.
2. Pastikan repository dapat di-pull oleh Render.
3. Pastikan tag `module12-v2` tersedia.
4. Catat repository, tag, image ID, dan digest bila registry menampilkannya.

> **Checkpoint 10:** Verified image tersedia di public registry dan tidak membawa `.env` atau generated database.

---

## Step 11 — Deploy Prebuilt Image ke Render Free

### Tujuan

Men-deploy exact registry image tanpa membangun ulang source code di cloud.

Di Render dashboard:

1. Pilih **New → Web Service → Existing Image**.
2. Masukkan `docker.io/<user>/northstar-agent:module12-v2`.
3. Pilih instance type **Free**.
4. Set health-check path ke `/health/ready`.
5. Tambahkan secret `API_KEY`.
6. Tambahkan `AGENT_MODEL`.
7. Tambahkan `API_BASE_URL` hanya jika diberikan instructor.
8. Tambahkan `APP_VERSION=module12-v2-render`.
9. Deploy service.

Jangan menambahkan `FORCE_READINESS_FAILURE=1` pada healthy release.

Setelah deploy selesai, buka:

- `https://<service>.onrender.com/health/ready`
- `https://<service>.onrender.com/version`
- `https://<service>.onrender.com/docs`
- `https://<service>.onrender.com/`

**Expected result:** Service ready, version adalah `module12-v2-render`, dan UI dapat menyelesaikan live request.

Jalankan public smoke test:

```bash
python scripts/smoke_test.py --base-url https://<service>.onrender.com
```

> **Checkpoint 11:** Catat public URL, public run ID, model, app version, image identity, dan smoke-test evidence.

### Render Free boundaries

- Service dapat sleep setelah inactive.
- Cold start dapat membutuhkan waktu sekitar satu menit.
- Local filesystem bersifat ephemeral.
- Free service tidak dapat horizontal scale.
- Model API usage tidak termasuk gratis hanya karena hosting menggunakan Free instance.

---

## Step 12 — Deploy Faulty Release dan Recover

### Tujuan

Membuktikan bahwa Anda dapat mengenali unready release dan memulihkan known-good image.

### 12.1 Record known-good evidence

Sebelum membuat failure, simpan:

- Known-good image tag dan ID/digest
- Successful public run ID
- `/health/ready` response
- `/version` response

### 12.2 Build intentional bad image

```bash
docker build --platform linux/amd64 --build-arg FORCE_READINESS_FAILURE=1 -t <user>/northstar-agent:module12-v2-bad .
docker push <user>/northstar-agent:module12-v2-bad
```

Build argument ini hanya membuat readiness gagal. Source code tidak perlu diubah.

### 12.3 Deploy bad tag

1. Update Render image reference menjadi `<user>/northstar-agent:module12-v2-bad`.
2. Trigger deployment.
3. Inspect deploy logs dan health-check evidence.
4. Capture readiness `503` atau failed-deploy health evidence.

Render dapat mempertahankan previous healthy deployment ketika release baru gagal health check. Yang harus dibuktikan adalah bad image gagal readiness, bukan bahwa public URL harus kehilangan service.

> **Important:** Jangan melakukan paid agent request saat readiness sudah gagal.

### 12.4 Restore known-good image

1. Kembalikan image reference ke `<user>/northstar-agent:module12-v2`.
2. Deploy ulang.
3. Pastikan `/health/ready` kembali `200`.
4. Pastikan `/version` kembali sesuai.
5. Jalankan tepat satu recovery smoke test:

```bash
python scripts/smoke_test.py --base-url https://<service>.onrender.com
```

**Expected result:** Bad release gagal readiness dan known-good release kembali menyelesaikan public agent run.

> **Checkpoint 12:** Anda memiliki failed-readiness evidence, known-good image identity, pre-failure run ID, dan post-recovery run ID.

---

## Submission Checklist

Submit artifact berikut tanpa secret:

- [ ] Public Render URL
- [ ] Registry repository dan tag
- [ ] Known-good image ID atau digest
- [ ] Screenshot UI yang menunjukkan sanitized tool evidence
- [ ] Swagger accepted request dan terminal response
- [ ] Local container smoke-test output
- [ ] Public smoke-test output sebelum failure
- [ ] Failed readiness atau failed-deploy evidence
- [ ] Public recovery smoke-test output
- [ ] Pre-failure dan post-recovery run ID
- [ ] Penjelasan singkat mengapa current in-memory run state tidak mendukung multiple replicas

## Reflection Questions

1. Mengapa liveness dan readiness tidak memanggil model API?
2. Mengapa model tidak boleh menjadi pemilik authorization decision?
3. Evidence apa yang menghubungkan source, image, deployment, dan public behavior?
4. Apa yang terjadi pada in-memory run state ketika container restart?
5. Komponen apa yang harus dipindahkan keluar sebelum horizontal scaling?

## Consolidated Troubleshooting

| Problem | Likely cause | Resolution |
|---|---|---|
| Missing model configuration | `.env` tidak lengkap | Isi `API_KEY` dan `AGENT_MODEL` |
| Provider `401/403` | Credential atau model access invalid | Gunakan key dan model yang disetujui instructor |
| Provider rate limit | Quota kelas atau request rate | Stop retry dan koordinasikan dengan instructor |
| API returns `422` | Payload tidak memenuhi Pydantic schema | Periksa required field dan identity combination |
| Readiness returns `503` | Missing config, data belum siap, atau deliberate failure | Baca `reasons`; perbaiki boundary terkait |
| Expected tool tidak dipilih | Model atau endpoint tidak kompatibel | Gunakan explicit test wording dan verifikasi function calling |
| Cancel terasa lambat | External request sedang in flight | Tunggu cancellation boundary berikutnya |
| Port already in use | Local server/container masih berjalan | Hentikan process atau gunakan host port lain |
| Docker cannot connect | Docker daemon berhenti | Start Docker Desktop/Engine |
| Render cannot pull image | Registry private, tag salah, atau architecture salah | Gunakan accessible image dan `linux/amd64` |
| Render cold start lambat | Free service sedang sleep | Tunggu startup sebelum menyimpulkan failure |
| Data hilang setelah restart | Render filesystem ephemeral | Gunakan managed shared storage untuk production |

## Cleanup

Setelah instructor menyetujui submission:

1. Stop local container dengan `Ctrl+C`.
2. Deactivate virtual environment dengan `deactivate`.
3. Hapus atau suspend Render classroom service bila tidak perlu online.
4. Remove classroom image dari public registry bila diminta instructor.
5. Rotate atau revoke classroom API key sesuai kebijakan instructor.

> **Production boundary:** Artifact kelas ini mendemonstrasikan productionization, tetapi belum merupakan production SLA system. Production implementation membutuhkan real authentication, durable queue, shared run/event store, managed database, idempotency, autoscaling, secret governance, rate limiting, audit controls, dan production telemetry.
