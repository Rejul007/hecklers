"""
app.py - FastAPI backend for the AI Onboarding Engine.

Endpoints:
  POST /api/sessions                          - create a new session
  GET  /api/sessions/{id}                     - get session data
  POST /api/sessions/{id}/resume/text         - upload resume as text
  POST /api/sessions/{id}/resume/file         - upload resume as PDF/text file
  POST /api/sessions/{id}/jd                  - submit job description
  POST /api/sessions/{id}/analyze             - run skill gap analysis
  POST /api/sessions/{id}/questionnaire/generate   - generate MCQ questionnaire
  POST /api/sessions/{id}/questionnaire/answer     - submit one answer
  POST /api/sessions/{id}/questionnaire/finish     - finish and score questionnaire
  POST /api/sessions/{id}/pathway/generate    - generate learning pathway
  GET  /api/sessions/{id}/pathway             - get pathway + skill progress
  POST /api/sessions/{id}/skills/{skill}/test/generate - generate skill test
  POST /api/sessions/{id}/skills/{skill}/test/submit   - submit skill test answers
  POST /api/sessions/{id}/skills/{skill}/status        - update skill status
  GET  /api/sessions/{id}/skills/{skill}/progress      - get skill test details
"""

import io
import os
from typing import Dict, Optional

import pdfplumber
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ai_engine
import database

load_dotenv()

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Onboarding Engine",
    description="Adaptive AI-powered employee onboarding with skill gap analysis and personalized learning pathways",
    version="1.0.0"
)

# CORS: allow all origins for development/demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize the database on application startup."""
    database.init_db()


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class TextInput(BaseModel):
    text: str


class AnswerInput(BaseModel):
    question_id: int
    answer: str  # "A", "B", "C", or "D"


class TestAnswersInput(BaseModel):
    answers: Dict[str, str]  # {str(question_id): letter}


class StatusInput(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sessions")
async def create_session():
    """Create a new onboarding session."""
    session_id = database.create_session()
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get all session data with all JSON fields parsed."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ---------------------------------------------------------------------------
# Resume endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/resume/text")
async def upload_resume_text(session_id: str, body: TextInput):
    """Parse resume from pasted text using Claude AI."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Resume text cannot be empty")

    try:
        resume_data = ai_engine.parse_resume(body.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    database.update_session(session_id, {
        "resume_text": body.text,
        "resume_data": resume_data,
        "candidate_name": resume_data.get("candidate_name", ""),
        "status": "resume_uploaded"
    })

    return {"resume_data": resume_data, "candidate_name": resume_data.get("candidate_name", "")}


@app.post("/api/sessions/{session_id}/resume/file")
async def upload_resume_file(session_id: str, file: UploadFile = File(...)):
    """Parse resume from uploaded PDF or text file using Claude AI."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = await file.read()
    filename = file.filename or ""

    # Extract text from PDF or plain text
    resume_text = ""
    if filename.lower().endswith(".pdf"):
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                resume_text = "\n".join(pages_text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to extract PDF text: {str(e)}")
    else:
        # Assume plain text (txt, doc, etc.)
        try:
            resume_text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                resume_text = content.decode("latin-1")
            except Exception:
                raise HTTPException(status_code=400, detail="Could not decode file. Please use PDF or UTF-8 text.")

    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    try:
        resume_data = ai_engine.parse_resume(resume_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    database.update_session(session_id, {
        "resume_text": resume_text,
        "resume_data": resume_data,
        "candidate_name": resume_data.get("candidate_name", ""),
        "status": "resume_uploaded"
    })

    return {"resume_data": resume_data, "candidate_name": resume_data.get("candidate_name", "")}


# ---------------------------------------------------------------------------
# Job Description endpoint
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/jd")
async def upload_jd(session_id: str, body: TextInput):
    """Parse job description using Claude AI."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Job description cannot be empty")

    try:
        jd_data = ai_engine.parse_job_description(body.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse job description: {str(e)}")

    database.update_session(session_id, {
        "jd_text": body.text,
        "jd_data": jd_data,
        "status": "jd_uploaded"
    })

    return {"jd_data": jd_data}


# ---------------------------------------------------------------------------
# Skill gap analysis endpoint
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/analyze")
async def analyze_skill_gap(session_id: str):
    """Run skill gap analysis comparing resume vs job description."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("resume_data"):
        raise HTTPException(status_code=400, detail="Resume not uploaded yet")
    if not session.get("jd_data"):
        raise HTTPException(status_code=400, detail="Job description not uploaded yet")

    try:
        skill_gaps = ai_engine.analyze_skill_gap(
            session["resume_data"],
            session["jd_data"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze skill gap: {str(e)}")

    database.update_session(session_id, {
        "skill_gaps": skill_gaps,
        "status": "analyzed"
    })

    return {"skill_gaps": skill_gaps}


# ---------------------------------------------------------------------------
# Questionnaire endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/questionnaire/generate")
async def generate_questionnaire(session_id: str):
    """Generate 35-40 adaptive MCQ questions covering all skill gaps."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("skill_gaps"):
        raise HTTPException(status_code=400, detail="Skill gap analysis not completed yet")

    try:
        questions = ai_engine.generate_questionnaire(
            session["skill_gaps"],
            session["resume_data"],
            session["jd_data"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate questionnaire: {str(e)}")

    # Initialize questionnaire state
    questionnaire_state = {
        "answers": {},        # {str(question_id): letter}
        "current_index": 0,   # index into questions list
        "completed": False
    }

    database.update_session(session_id, {
        "questionnaire_questions": questions,
        "questionnaire_state": questionnaire_state,
        "status": "questionnaire"
    })

    # Identify all unique skills being assessed
    skills_assessed = list(set(q["skill"] for q in questions))

    return {
        "questions": questions,
        "first_question": questions[0] if questions else None,
        "total_questions": len(questions),
        "skills_being_assessed": skills_assessed
    }


@app.post("/api/sessions/{session_id}/questionnaire/answer")
async def submit_answer(session_id: str, body: AnswerInput):
    """
    Submit an answer to a questionnaire question.
    Returns immediate feedback and the next question.
    """
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    questions = session.get("questionnaire_questions")
    state = session.get("questionnaire_state")

    if not questions or not state:
        raise HTTPException(status_code=400, detail="Questionnaire not started yet")

    # Find the question being answered
    q_id = body.question_id
    question = next((q for q in questions if q["id"] == q_id), None)
    if not question:
        raise HTTPException(status_code=404, detail=f"Question {q_id} not found")

    # Validate answer
    if body.answer not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail="Answer must be A, B, C, or D")

    # Record the answer
    state["answers"][str(q_id)] = body.answer

    # Determine correctness
    correct_answer = question.get("correct_answer", "")
    is_correct = body.answer == correct_answer

    # Find next unanswered question
    answered_ids = set(state["answers"].keys())
    next_question = None
    next_index = None
    for i, q in enumerate(questions):
        if str(q["id"]) not in answered_ids:
            next_question = q
            next_index = i
            break

    if next_question:
        state["current_index"] = next_index
    else:
        state["completed"] = True

    # Save updated state
    database.update_session(session_id, {"questionnaire_state": state})

    # Calculate progress
    answered_count = len(state["answers"])
    total_count = len(questions)
    progress_pct = round((answered_count / total_count) * 100) if total_count > 0 else 0

    return {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "explanation": question.get("explanation", ""),
        "next_question": next_question,
        "progress": {
            "answered": answered_count,
            "total": total_count,
            "percentage": progress_pct,
            "completed": state["completed"]
        }
    }


@app.post("/api/sessions/{session_id}/questionnaire/finish")
async def finish_questionnaire(session_id: str):
    """Calculate proficiency scores after completing the questionnaire."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    questions = session.get("questionnaire_questions")
    state = session.get("questionnaire_state")

    if not questions or not state:
        raise HTTPException(status_code=400, detail="Questionnaire not started")

    answers = state.get("answers", {})

    proficiency_scores = ai_engine.calculate_proficiency_scores(questions, answers)

    database.update_session(session_id, {
        "proficiency_scores": proficiency_scores,
        "status": "scored"
    })

    return {"proficiency_scores": proficiency_scores}


# ---------------------------------------------------------------------------
# Learning pathway endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/pathway/generate")
async def generate_pathway(session_id: str):
    """Generate personalized learning pathway and initialize skill tests."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("proficiency_scores"):
        raise HTTPException(status_code=400, detail="Proficiency scores not calculated yet")

    try:
        pathway = ai_engine.generate_learning_pathway(
            session["proficiency_scores"],
            session["skill_gaps"],
            session["resume_data"],
            session["jd_data"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate pathway: {str(e)}")

    # Initialize skill test records for each skill in the pathway
    for skill_entry in pathway.get("skills", []):
        skill_name = skill_entry.get("skill_name", "")
        if skill_name:
            database.upsert_skill_test(session_id, skill_name, {
                "status": "not_started",
                "questions": None,
                "answers": None,
                "score": 0,
                "passed": 0,
                "attempts": 0,
                "feedback": None
            })

    database.update_session(session_id, {
        "pathway": pathway,
        "status": "pathway"
    })

    return {"pathway": pathway}


@app.get("/api/sessions/{session_id}/pathway")
async def get_pathway(session_id: str):
    """Get the learning pathway along with per-skill test progress."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("pathway"):
        raise HTTPException(status_code=404, detail="Pathway not generated yet")

    skill_tests = database.get_all_skill_tests(session_id)

    # Build a progress summary per skill
    skill_progress = {
        test["skill_name"]: {
            "status": test["status"],
            "score": test["score"],
            "passed": test["passed"],
            "attempts": test["attempts"]
        }
        for test in skill_tests
    }

    return {
        "pathway": session["pathway"],
        "skill_progress": skill_progress
    }


# ---------------------------------------------------------------------------
# Skill test endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/skills/{skill_name}/test/generate")
async def generate_skill_test(session_id: str, skill_name: str):
    """Generate 8 verification MCQs for a specific skill."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Find target level from pathway
    pathway = session.get("pathway", {})
    target_level = "intermediate"  # default
    for skill_entry in pathway.get("skills", []):
        if skill_entry.get("skill_name", "").lower() == skill_name.lower():
            target_level = skill_entry.get("target_level", "intermediate")
            break

    try:
        questions = ai_engine.generate_skill_test(skill_name, target_level)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate skill test: {str(e)}")

    database.upsert_skill_test(session_id, skill_name, {
        "status": "testing",
        "questions": questions,
        "answers": {},
        "score": 0,
        "passed": 0
    })

    return {
        "questions": questions,
        "target_level": target_level,
        "total_questions": len(questions)
    }


@app.post("/api/sessions/{session_id}/skills/{skill_name}/test/submit")
async def submit_skill_test(session_id: str, skill_name: str, body: TestAnswersInput):
    """Submit all answers for a skill test and get evaluation + feedback."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    skill_test = database.get_skill_test(session_id, skill_name)
    if not skill_test or not skill_test.get("questions"):
        raise HTTPException(status_code=400, detail="Skill test not generated yet")

    questions = skill_test["questions"]

    # Find target level from pathway
    pathway = session.get("pathway", {})
    target_level = "intermediate"
    for skill_entry in pathway.get("skills", []):
        if skill_entry.get("skill_name", "").lower() == skill_name.lower():
            target_level = skill_entry.get("target_level", "intermediate")
            break

    try:
        result = ai_engine.evaluate_skill_test(
            skill_name,
            questions,
            body.answers,
            target_level
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate test: {str(e)}")

    # Determine new status
    new_status = "completed" if result["passed"] else "needs_revision"
    attempts = (skill_test.get("attempts") or 0) + 1

    database.upsert_skill_test(session_id, skill_name, {
        "status": new_status,
        "answers": body.answers,
        "score": result["score"],
        "passed": 1 if result["passed"] else 0,
        "attempts": attempts,
        "feedback": result["feedback"]
    })

    return {
        "result": result,
        "new_status": new_status,
        "attempts": attempts
    }


@app.post("/api/sessions/{session_id}/skills/{skill_name}/status")
async def update_skill_status(session_id: str, skill_name: str, body: StatusInput):
    """Manually update the status of a skill (e.g., mark as 'learning')."""
    valid_statuses = {"not_started", "learning", "testing", "completed", "needs_revision"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    database.upsert_skill_test(session_id, skill_name, {"status": body.status})

    return {"skill_name": skill_name, "status": body.status}


@app.get("/api/sessions/{session_id}/skills/{skill_name}/progress")
async def get_skill_progress(session_id: str, skill_name: str):
    """Get detailed skill test progress including questions and results."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    skill_test = database.get_skill_test(session_id, skill_name)
    if not skill_test:
        raise HTTPException(status_code=404, detail="Skill test record not found")

    return skill_test


# ---------------------------------------------------------------------------
# Static file serving (SPA)
# ---------------------------------------------------------------------------

# Serve the frontend SPA from the static/ directory
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
