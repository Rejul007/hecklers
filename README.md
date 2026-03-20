# AI Onboarding Engine

> An adaptive, AI-powered employee onboarding platform that analyzes skill gaps, generates personalized assessments, and creates customized learning pathways — powered by Claude claude-opus-4-6.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (SPA)                            │
│  Tailwind CSS + Vanilla JS + Font Awesome                        │
│  Views: Welcome → Setup → Analysis → Questionnaire →            │
│         Results → Pathway → Skill Tests                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / JSON
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (app.py)                      │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  REST API Endpoints                                       │    │
│  │  POST /api/sessions                                       │    │
│  │  GET  /api/sessions/{id}                                  │    │
│  │  POST /api/sessions/{id}/resume/text                      │    │
│  │  POST /api/sessions/{id}/resume/file  (PDF/txt)           │    │
│  │  POST /api/sessions/{id}/jd                               │    │
│  │  POST /api/sessions/{id}/analyze                          │    │
│  │  POST /api/sessions/{id}/questionnaire/generate           │    │
│  │  POST /api/sessions/{id}/questionnaire/answer             │    │
│  │  POST /api/sessions/{id}/questionnaire/finish             │    │
│  │  POST /api/sessions/{id}/pathway/generate                 │    │
│  │  GET  /api/sessions/{id}/pathway                          │    │
│  │  POST /api/sessions/{id}/skills/{name}/test/generate      │    │
│  │  POST /api/sessions/{id}/skills/{name}/test/submit        │    │
│  │  POST /api/sessions/{id}/skills/{name}/status             │    │
│  │  GET  /api/sessions/{id}/skills/{name}/progress           │    │
│  └───────────────────┬─────────────────────────────────────┘    │
└──────────────────────┼──────────────────────────────────────────┘
                       │
         ┌─────────────┴──────────────┐
         ▼                            ▼
┌────────────────────┐   ┌────────────────────────────────────────┐
│   SQLite DB        │   │   Claude claude-opus-4-6 (ai_engine.py)│
│   (database.py)    │   │                                        │
│                    │   │  parse_resume()          ← thinking    │
│  sessions table    │   │  parse_job_description() ← thinking    │
│  skill_tests table │   │  analyze_skill_gap()     ← thinking    │
│                    │   │  generate_questionnaire()← thinking    │
│  JSON fields for:  │   │  calculate_proficiency_scores()        │
│  - resume_data     │   │  generate_learning_pathway()← thinking │
│  - jd_data         │   │  generate_skill_test()   ← thinking    │
│  - skill_gaps      │   │  evaluate_skill_test()                 │
│  - questions       │   └────────────────────────────────────────┘
│  - pathway         │
└────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Model | **Claude claude-opus-4-6** (Anthropic) with adaptive thinking |
| Backend | **FastAPI** (Python 3.11+) |
| Database | **SQLite** via Python's built-in `sqlite3` |
| PDF Parsing | **pdfplumber** |
| Frontend | **Vanilla JavaScript** + **Tailwind CSS v3** (CDN) + **Font Awesome 6** |
| Serving | **Uvicorn** ASGI server |
| Containerization | **Docker** (multi-stage build) |

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- An Anthropic API key ([get one here](https://console.anthropic.com/))

### Local Development

```bash
# 1. Clone the repository
git clone <repo-url>
cd hecklers

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 5. Run the server
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# 6. Open the app
open http://localhost:8000
```

### Docker

```bash
# Build the image
docker build -t ai-onboarding-engine .

# Run with your API key
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key_here ai-onboarding-engine

# Or with a mounted volume for SQLite persistence
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=your_key_here \
  -v $(pwd)/data:/app/data \
  ai-onboarding-engine
```

---

## How It Works

### 1. Skill Gap Analysis Logic

When a candidate submits their resume and a recruiter provides a job description, Claude performs a three-step analysis:

1. **Resume Parsing**: Claude extracts skills with proficiency levels (beginner → expert), work experience with durations, education, and calculates total years of experience.

2. **JD Parsing**: Claude extracts required skills with importance levels (required / preferred / nice_to_have), responsibilities, and experience requirements.

3. **Gap Analysis**: Claude compares the two profiles and produces:
   - **Overall Fit Score** (0–100): weighted match across all required skills
   - **Strong Matches**: skills where candidate meets or exceeds requirements
   - **Skill Gaps**: detailed gap per skill with severity (critical/high/medium/low) and reasoning
   - **Missing Skills**: skills with zero evidence in the resume

### 2. Adaptive Questionnaire

The questionnaire is dynamically generated by Claude based on the specific skill gaps:

- **35–40 MCQ questions** distributed across all gap skills
- Questions at **three difficulty levels**: basic, intermediate, advanced
- Skills with critical/high gaps receive more questions (5–7)
- Skills with medium/low gaps receive fewer questions (3–4)
- Questions are presented **one at a time** with immediate feedback
- After each answer, a 2.5-second window shows correctness + explanation before auto-advancing
- **Scoring**: weighted average where basic=1x, intermediate=2x, advanced=3x weight

### 3. Proficiency Score Calculation

After the questionnaire, proficiency is calculated per skill:

```
basic_accuracy    = correct_basic / total_basic * 100
inter_accuracy    = correct_inter / total_inter * 100
advanced_accuracy = correct_adv   / total_adv   * 100

weighted_score = (basic_acc * 1 + inter_acc * 2 + adv_acc * 3) / (1+2+3)

Level assignment:
  ≥85% → advanced
  ≥65% → intermediate
  ≥40% → basic
   <40% → beginner
```

### 4. Personalized Learning Pathway

Claude generates a week-by-week learning plan for each skill gap:

- **Learning order** optimized for prerequisites (foundational skills first)
- **3–5 curated resources** per skill (courses, books, practice platforms, docs)
- **Week-by-week breakdown** with specific tasks and milestones
- **Practice project** suggestion for hands-on application
- **Estimated timeline** based on gap severity and target level

### 5. Skill Verification Tests

For each skill in the pathway:

- Claude generates **8 scenario-based MCQs** at the target proficiency level
- Candidate answers all 8 questions
- **Pass threshold: 75%** (6/8 correct)
- Claude generates **personalized feedback** based on wrong answers
- Failed skills enter "needs_revision" status and can be retested
- Passed skills are marked complete with a visual indicator

---

## API Endpoints Reference

### Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions` | Create new session |
| GET | `/api/sessions/{id}` | Get full session data |

### Resume & JD
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions/{id}/resume/text` | Upload resume as text |
| POST | `/api/sessions/{id}/resume/file` | Upload PDF/txt file |
| POST | `/api/sessions/{id}/jd` | Submit job description |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions/{id}/analyze` | Run skill gap analysis |

### Questionnaire
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions/{id}/questionnaire/generate` | Generate 35–40 MCQs |
| POST | `/api/sessions/{id}/questionnaire/answer` | Submit one answer |
| POST | `/api/sessions/{id}/questionnaire/finish` | Calculate proficiency scores |

### Pathway
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions/{id}/pathway/generate` | Generate learning pathway |
| GET | `/api/sessions/{id}/pathway` | Get pathway + skill progress |

### Skill Tests
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions/{id}/skills/{name}/test/generate` | Generate 8-question test |
| POST | `/api/sessions/{id}/skills/{name}/test/submit` | Submit answers + evaluate |
| POST | `/api/sessions/{id}/skills/{name}/status` | Update skill status |
| GET | `/api/sessions/{id}/skills/{name}/progress` | Get skill test details |

---

## Citations & Inspirations

- **AI Model**: [Claude claude-opus-4-6](https://www.anthropic.com/claude) by Anthropic — used for all NLP, reasoning, and generation tasks
- **Skill taxonomy**: Inspired by [O*NET Online](https://www.onetonline.org/) occupational skill databases
- **Resume datasets**: Methodology inspired by [Kaggle Resume Dataset](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset) for skill extraction patterns
- **Learning resources**: Curated from real platforms (Coursera, edX, Udemy, O'Reilly, Kaggle)
- **Gap analysis methodology**: Based on competency framework literature from SHRM (Society for Human Resource Management)

---

## Project Structure

```
hecklers/
├── app.py              # FastAPI application + all API endpoints
├── ai_engine.py        # Claude AI integration (all AI functions)
├── database.py         # SQLite operations (init, CRUD)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Multi-stage production Docker build
├── .env.example        # Environment variable template
├── README.md           # This file
└── static/
    └── index.html      # Complete SPA (HTML + CSS + JS, ~1000 lines)
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key from console.anthropic.com |

---

## Hackathon Notes

This project demonstrates:

1. **Claude's reasoning capabilities**: Using adaptive thinking for nuanced skill gap analysis and curriculum design
2. **Full-stack integration**: FastAPI backend cleanly separating AI logic, data persistence, and HTTP handling
3. **Production-ready patterns**: Proper error handling, JSON parsing robustness, session management
4. **UX polish**: Loading states for 10–30 second AI calls, real-time feedback, progress tracking
5. **Extensibility**: Modular design where each AI function can be improved independently
