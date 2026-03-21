# AI Onboarding Engine

> An adaptive, AI-powered employee onboarding platform that analyzes skill gaps, generates personalized assessments, and creates customized learning pathways — powered by Ollama (Qwen2.5:7b) running entirely offline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (SPA)                            │
│    Tailwind CSS + Vanilla JS + Font Awesome + Firebase Auth     │
│      Views: Welcome → Setup → Analysis → Questionnaire →        │
│                Results → Pathway → Skill Tests                  │
│                                                                 │
│  /manager.html  — Manager dashboard (Firebase auth)             │
│  /admin.html    — Admin panel (password protected)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / JSON
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (app.py)                     │
│                                                                 │
│  Employee endpoints  /api/sessions/...                          │
│  Manager endpoints   /api/manager/...                           │
│  Admin endpoints     /api/admin/...                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
             ┌─────────────┴──────────────┐
             ▼                            ▼
┌────────────────────┐   ┌────────────────────────────────────────┐
│   SQLite DB        │   │   Ollama (ai_engine.py)                │
│   (database.py)    │   │   Model: qwen2.5:7b                    │
│                    │   │                                        │
│  sessions          │   │  parse_resume()                        │
│  skill_tests       │   │  parse_job_description()               │
│  managers          │   │  analyze_skill_gap()                   │
│  manager_sessions  │   │  generate_questionnaire()              │
│                    │   │  calculate_proficiency_scores()        │
│                    │   │  generate_learning_pathway()           │
│                    │   │  generate_skill_test()                 │
│                    │   │  evaluate_skill_test()                 │
└────────────────────┘   └────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Model | **Qwen2.5:7b** via **Ollama** (runs fully offline, no API key needed) |
| Backend | **FastAPI** (Python 3.11+) |
| Database | **SQLite** via Python's built-in `sqlite3` |
| PDF Parsing | **pdfplumber** |
| Auth | **Firebase Authentication** (Google sign-in + email/password) |
| Frontend | **Vanilla JavaScript** + **Tailwind CSS** (CDN) + **Font Awesome 6** |
| Serving | **Uvicorn** ASGI server |
| Containerization | **Docker** + **Docker Compose** |

---

## Setup

### Option 1 — start.sh (recommended for local use)

```bash
# 1. Clone the repository
git clone https://github.com/Rejul007/hecklers.git
cd hecklers

# 2. Configure environment
cp .env.example .env
# Edit .env and set your ADMIN_PASSWORD

# 3. Start everything (installs deps, pulls model, starts server)
bash start.sh
```

`start.sh` will automatically:
- Create a Python virtual environment
- Install all Python dependencies
- Install Ollama if not present
- Pull the qwen2.5:7b model if not already downloaded (~4.7 GB, first run only)
- Start the FastAPI server on port 8000

### Option 2 — Docker Compose (recommended for servers)

```bash
# 1. Clone the repository
git clone https://github.com/Rejul007/hecklers.git
cd hecklers

# 2. Configure environment
cp .env.example .env
# Edit .env and set your ADMIN_PASSWORD

# 3. Build and start
docker compose up --build

# Subsequent starts (no rebuild needed)
docker compose up
```

Docker Compose persists:
- The Ollama model cache (no re-downloading on restart)
- The SQLite database (no data loss on restart)

App will be available at `http://localhost:8000`.

---

## Pages

| URL | Description | Access |
|-----|-------------|--------|
| `/` | Employee onboarding app | Firebase auth (Google / email) |
| `/manager.html` | Manager dashboard — view all employees, skill gaps, progress | Firebase auth + manager whitelist |
| `/admin.html` | Admin panel — add/remove managers | Admin password from `.env` |

---

## How It Works

### 1. Skill Gap Analysis

When a candidate submits their resume and a job description:

1. **Resume Parsing** — extracts skills with proficiency levels, work experience, education
2. **JD Parsing** — extracts required skills with importance levels (required / preferred / nice_to_have)
3. **Gap Analysis** — produces:
   - **Overall Fit Score** (0–100)
   - **Strong Matches** — skills where candidate meets or exceeds requirements
   - **Skill Gaps** — per-skill severity (critical / high / medium / low) with reasoning
   - **Missing Skills** — skills with zero evidence in the resume

### 2. Adaptive Questionnaire

- **35–40 MCQ questions** across all gap skills
- Three difficulty levels: basic, intermediate, advanced
- Critical/high gaps get more questions (5–7); medium/low get fewer (3–4)
- Scoring: basic=1x, intermediate=2x, advanced=3x weight

### 3. Proficiency Score Calculation

```
weighted_score = (basic_acc×1 + inter_acc×2 + adv_acc×3) / 6

Level:  ≥85% → advanced
        ≥65% → intermediate
        ≥40% → basic
        <40% → beginner
```

### 4. Personalized Learning Pathway

- Learning order optimized for prerequisites (foundational skills first)
- Week-by-week breakdown with specific tasks and milestones
- Practice project per skill
- Estimated timeline based on gap severity

### 5. Skill Verification Tests

- 8 scenario-based MCQs per skill at the target proficiency level
- Pass threshold: 75% (6/8 correct)
- Personalized feedback on wrong answers
- Failed skills enter "needs_revision" and can be retested

---

## API Endpoints

### Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions` | Create new session |
| GET | `/api/sessions/{id}` | Get full session data |
| POST | `/api/sessions/{id}/resume/text` | Upload resume as text |
| POST | `/api/sessions/{id}/resume/file` | Upload PDF/txt file |
| POST | `/api/sessions/{id}/jd` | Submit job description |
| POST | `/api/sessions/{id}/analyze` | Run skill gap analysis |
| POST | `/api/sessions/{id}/questionnaire/generate` | Generate MCQs |
| POST | `/api/sessions/{id}/questionnaire/answer` | Submit one answer |
| POST | `/api/sessions/{id}/questionnaire/finish` | Calculate proficiency scores |
| POST | `/api/sessions/{id}/pathway/generate` | Generate learning pathway |
| GET | `/api/sessions/{id}/pathway` | Get pathway + skill progress |
| POST | `/api/sessions/{id}/skills/{name}/test/generate` | Generate skill test |
| POST | `/api/sessions/{id}/skills/{name}/test/submit` | Submit + evaluate test |
| POST | `/api/sessions/{id}/skills/{name}/status` | Update skill status |
| GET | `/api/sessions/{id}/skills/{name}/progress` | Get skill test details |
| POST | `/api/sessions/{id}/link-user` | Link Firebase user to session |

### Manager
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/manager/login` | Verify whitelist + issue session token |
| POST | `/api/manager/logout` | Invalidate session token |
| GET | `/api/manager/dashboard` | Get all employee data |
| DELETE | `/api/manager/employees/{session_id}` | Remove an employee |

### Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/login` | Verify admin password + issue token |
| POST | `/api/admin/logout` | Invalidate admin token |
| GET | `/api/admin/managers` | List all whitelisted managers |
| POST | `/api/admin/managers` | Add manager to whitelist |
| DELETE | `/api/admin/managers/{email}` | Remove manager from whitelist |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_PASSWORD` | Yes | Password for the `/admin.html` page |
| `DB_PATH` | No | SQLite file path (default: `onboarding.db`, set to `/app/data/onboarding.db` in Docker) |

---

## Project Structure

```
hecklers/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application + all API endpoints
│   ├── ai_engine.py      # Ollama AI integration (all AI functions)
│   └── database.py       # SQLite operations (init, CRUD)
├── static/
│   ├── index.html        # Employee onboarding SPA
│   ├── manager.html      # Manager dashboard
│   └── admin.html        # Admin panel
├── requirements.txt      # Python dependencies
├── start.sh              # One-command local startup script
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose with persistent volumes
├── .env.example          # Environment variable template
└── README.md             # This file
```
