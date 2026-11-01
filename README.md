# PodMentor

PodMentor is a cost-aware AI assistant that helps SRE trainees understand the Kubernetes source codebase by routing questions to the most suitable language model.

## Problem

SRE trainees preparing for Kubernetes on-call responsibilities and CKA-style interviews often struggle to navigate the large Kubernetes codebase. With more than 17,000 Go source files, finding the correct implementation for a specific feature can be time-consuming. Simple lookup questions do not always require an expensive reasoning model, but sending every question to a powerful model can quickly exhaust free-tier limits. PodMentor solves this problem by routing questions to the cheapest suitable model while reserving stronger models for complex reasoning tasks.

## Who it is for

- SRE trainees at cloud-managed-services companies preparing for Kubernetes on-call responsibilities.
- Junior DevOps engineers preparing for Kubernetes and CKA-style technical interviews.

## Signature feature

**Cost-aware model routing:** PodMentor classifies questions and routes simple code lookups to a fast, inexpensive model (`gemini-1.5-flash`) while preserving an automated fallback model (`gemini-1.5-flash-8b`) on transient errors/rate limits, and reserving stronger models for complex reasoning tasks.

## Hardest problem (my interview story)

The main challenge is designing a routing system that identifies whether a question requires simple code retrieval or deeper reasoning. Routing every question to a powerful model increases cost, while routing complex questions to a smaller model may reduce answer quality. PodMentor aims to balance these trade-offs by selecting an appropriate model for each question and evaluating cost, latency, and answer quality.

## System Design & Database Schema

See [DESIGN.md](DESIGN.md) for detailed documentation on:
- API endpoint specifications and JSON schemas
- Database tables (`usage_logs`, `documents`, `document_chunks`)
- Entity Relationship (ER) diagrams
- Resilient fallback sequence diagrams and Gemini pricing rate cards

## Dataset

| Source | Link | Documents | Pages | Licence / terms |
|---|---|---|---|---|
| Kubernetes source code | [GitHub – kubernetes/kubernetes](https://github.com/kubernetes/kubernetes) | 17,000+ Go source files (minimum target) | N/A — source code repository | Apache License 2.0 |

*Note: The file count is a project target from the project card, not a verified current repository count. Update it after measuring the actual dataset used.*

## 10 real questions

See [docs/QUESTIONS.md](docs/QUESTIONS.md) for the 10 real questions used to test PodMentor.

Example questions:

1. Where is the pod eviction code implemented?
2. Where is the Kubernetes scheduler defined?
3. Which component communicates with the container runtime?
4. Where is the API server request handler implemented?
5. How does the kubelet manage pods?
6. Where are Kubernetes controllers implemented?
7. How does Kubernetes schedule a pod onto a node?
8. Why might a pod remain in the Pending state?
9. How does Kubernetes recover from a node failure?
10. How does the scheduler make placement decisions when multiple constraints apply?

---

## Run it

### Option A: Local Development

#### 1. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python -m venv .venv
source .venv/bin/activate
```

#### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
```

#### 3. Configure environment variables

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

To enable live Google Gemini calls, set `GEMINI_API_KEY=AIza...` in `.env`. If left empty, PodMentor automatically runs in offline/mock mode for seamless testing.

#### 4. Start the application

```bash
uvicorn app.main:app --reload
```

---

### Option B: Docker Container

Build and run the standalone containerized service:

```bash
# Build the Docker image
docker build -t podmentor .

# Run the container (with optional GEMINI_API_KEY)
docker run -p 8000:8000 -e GEMINI_API_KEY=AIza... podmentor
```

Check the health probe:
```bash
curl http://localhost:8000/health
```

---

### Option C: Docker Compose (API + Postgres/pgvector)

Run the full application stack including PostgreSQL with `pgvector`:

```bash
docker compose up -d
```

Verify services are up and healthy:
```bash
docker compose ps
```

---

## Testing & Quality Assurance

Run the test suite and linter:

```bash
# Run automated tests
pytest -v

# Run Ruff linter
ruff check .
```

---

## API Endpoints

### 1. `GET /health`
Liveness probe. Fast response, zero LLM or DB dependencies.

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{"status": "ok", "app": "podmentor", "environment": "local"}
```

### 2. `POST /chat`
Submits a query to the model routing gateway. Supports automatic fallback model switching and streaming chunks via Server-Sent Events (SSE).

**JSON Mode:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Where is the pod eviction code implemented in Kubernetes?", "stream": false}'
```

**Streaming Mode (SSE):**
```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How does kubelet manage pod lifecycles?", "stream": true}'
```

### 3. `GET /usage`
Returns token totals (prompt, completion, total), cumulative USD expenditure, and breakdown by model.

```bash
curl http://localhost:8000/usage
```

---

## Live link

PodMentor is configured for 1-click zero-cost deployment on Render using the included [`render.yaml`](render.yaml) blueprint:

- **Live Host URL:** `https://podmentor.onrender.com`
- **Live Health Check:** [`https://podmentor.onrender.com/health`](https://podmentor.onrender.com/health)

*(To deploy your own live instance: connect this repo on [render.com](https://render.com), select "New Web Service", and deploy with Docker runtime for free).*
