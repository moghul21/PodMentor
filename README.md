# PodMentor

PodMentor is a cost-aware AI assistant that helps SRE trainees understand the Kubernetes source codebase by routing questions to the most suitable language model.

## Problem

SRE trainees preparing for Kubernetes on-call responsibilities and CKA-style interviews often struggle to navigate the large Kubernetes codebase. With more than 17,000 Go source files, finding the correct implementation for a specific feature can be time-consuming. Simple lookup questions do not always require an expensive reasoning model, but sending every question to a powerful model can quickly exhaust free-tier limits. PodMentor solves this problem by routing questions to the cheapest suitable model while reserving stronger models for complex reasoning tasks.

## Who it is for

- SRE trainees at cloud-managed-services companies preparing for Kubernetes on-call responsibilities.
- Junior DevOps engineers preparing for Kubernetes and CKA-style technical interviews.

## Signature feature

**Cost-aware model routing:** PodMentor classifies questions and routes simple code lookups to a fast, inexpensive model while sending complex reasoning questions to a stronger model, helping balance cost, latency, and answer quality.

## Hardest problem (my interview story)

The main challenge is designing a routing system that identifies whether a question requires simple code retrieval or deeper reasoning. Routing every question to a powerful model increases cost, while routing complex questions to a smaller model may reduce answer quality. PodMentor aims to balance these trade-offs by selecting an appropriate model for each question and evaluating cost, latency, and answer quality.

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

## Run it

### 1. Create and activate a virtual environment

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

### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
```

### 3. Configure environment variables

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Add the required model-provider API keys and configuration to `.env`, if needed.

### 4. Start the application

```bash
uvicorn app.main:app --reload
```

### 5. Check the health endpoint

```bash
curl http://localhost:8000/health
```

Expected result: a successful health response from the application.

*These commands assume the repository contains `app/main.py`, `requirements-dev.txt`, `.env.example`, and the `/health` endpoint.*

## Live link

Coming in Week 2.
