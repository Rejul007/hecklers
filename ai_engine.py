"""
ai_engine.py - Claude AI integration for the AI Onboarding Engine.

All functions use the Anthropic SDK with claude-opus-4-6.
Adaptive thinking is enabled for complex reasoning tasks (gap analysis,
questionnaire generation, pathway generation, skill test generation).

Key design decisions:
- Adaptive thinking uses {"type": "adaptive"} (budget_tokens is deprecated on opus-4)
- Response content may contain ThinkingBlock + TextBlock; we always extract the TextBlock
- JSON is parsed with markdown fence stripping for robustness
"""

import json
import re
import os
from typing import Any, Dict, List, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Initialize the Anthropic client once (reads ANTHROPIC_API_KEY from env)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MODEL = "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _extract_text_block(content: list) -> str:
    """
    Extract the text from a Claude response that may contain thinking blocks.
    ThinkingBlock objects have a 'thinking' attribute but NOT 'text'.
    TextBlock objects have a 'text' attribute.
    We skip all thinking blocks and return the first text block.
    """
    for block in content:
        if hasattr(block, "text"):
            return block.text
    return ""


def _parse_json_response(text: str) -> Any:
    """
    Parse a JSON response from Claude, stripping markdown code fences if present.
    Claude sometimes wraps output in ```json ... ``` blocks.
    """
    # Strip leading/trailing whitespace
    text = text.strip()

    # Remove ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to find JSON object/array within the text as a fallback
        json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from Claude response: {e}\nText was: {text[:500]}")


# ---------------------------------------------------------------------------
# Core AI Functions
# ---------------------------------------------------------------------------

def parse_resume(text: str) -> Dict[str, Any]:
    """
    Extract structured information from resume text using Claude.
    Uses adaptive thinking for more accurate extraction.

    Returns:
        {
            candidate_name: str,
            skills: [{name, proficiency, years}],
            work_experience: [{company, title, duration, description}],
            education: [{degree, institution, year}],
            total_experience_years: float
        }
    """
    prompt = f"""You are an expert HR analyst and resume parser. Analyze the following resume text and extract structured information.

RESUME TEXT:
{text}

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
    "candidate_name": "Full Name",
    "skills": [
        {{"name": "Python", "proficiency": "advanced", "years": 5}},
        {{"name": "Machine Learning", "proficiency": "intermediate", "years": 2}}
    ],
    "work_experience": [
        {{
            "company": "Company Name",
            "title": "Job Title",
            "duration": "2020-2023",
            "description": "Brief description of responsibilities and achievements"
        }}
    ],
    "education": [
        {{
            "degree": "Bachelor of Science in Computer Science",
            "institution": "University Name",
            "year": "2019"
        }}
    ],
    "total_experience_years": 4.5
}}

Rules:
- proficiency must be one of: beginner, basic, intermediate, advanced, expert
- years should be a number (0 if unknown)
- total_experience_years should be the sum of professional experience
- Extract ALL skills mentioned, including soft skills and domain knowledge
- If information is missing, use reasonable defaults or empty arrays
- Return ONLY the JSON, nothing else"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )

    text_response = _extract_text_block(response.content)
    return _parse_json_response(text_response)


def parse_job_description(text: str) -> Dict[str, Any]:
    """
    Extract structured information from a job description using Claude.

    Returns:
        {
            role_title: str,
            required_skills: [{name, level, importance}],
            responsibilities: [str],
            required_experience_years: float
        }
    """
    prompt = f"""You are an expert HR analyst and job description parser. Analyze the following job description and extract structured information.

JOB DESCRIPTION:
{text}

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
    "role_title": "Senior Software Engineer",
    "required_skills": [
        {{"name": "Python", "level": "advanced", "importance": "required"}},
        {{"name": "AWS", "level": "intermediate", "importance": "preferred"}},
        {{"name": "Docker", "level": "basic", "importance": "nice_to_have"}}
    ],
    "responsibilities": [
        "Design and implement scalable microservices",
        "Collaborate with cross-functional teams",
        "Mentor junior developers"
    ],
    "required_experience_years": 5.0
}}

Rules:
- level must be one of: basic, intermediate, advanced, expert
- importance must be one of: required, preferred, nice_to_have
- List ALL skills mentioned, including tools, frameworks, methodologies
- Extract specific years of experience if mentioned
- responsibilities should be concise bullet points
- Return ONLY the JSON, nothing else"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )

    text_response = _extract_text_block(response.content)
    return _parse_json_response(text_response)


def analyze_skill_gap(resume_data: Dict, jd_data: Dict) -> Dict[str, Any]:
    """
    Perform a detailed skill gap analysis comparing candidate's resume to job requirements.
    Uses adaptive thinking for nuanced reasoning.

    Returns:
        {
            overall_fit_score: int (0-100),
            strong_matches: [str],
            skill_gaps: [{skill, candidate_level, required_level, gap_severity, priority, reason}],
            missing_skills: [str],
            summary: str
        }
    """
    prompt = f"""You are an expert talent acquisition specialist performing a comprehensive skill gap analysis.

CANDIDATE PROFILE:
{json.dumps(resume_data, indent=2)}

JOB REQUIREMENTS:
{json.dumps(jd_data, indent=2)}

Perform a thorough analysis and return ONLY a valid JSON object with this exact structure:
{{
    "overall_fit_score": 72,
    "strong_matches": ["Python", "SQL", "Data Analysis"],
    "skill_gaps": [
        {{
            "skill": "Machine Learning",
            "candidate_level": "basic",
            "required_level": "advanced",
            "gap_severity": "high",
            "priority": 1,
            "reason": "Core requirement for role; candidate has theoretical knowledge but lacks production ML experience"
        }},
        {{
            "skill": "Kubernetes",
            "candidate_level": "none",
            "required_level": "intermediate",
            "gap_severity": "medium",
            "priority": 2,
            "reason": "Required for deployment pipelines; no experience detected"
        }}
    ],
    "missing_skills": ["GraphQL", "Terraform"],
    "summary": "The candidate shows strong programming fundamentals but needs significant upskilling in ML engineering and cloud infrastructure to meet role requirements."
}}

Rules:
- overall_fit_score: 0-100 based on how well candidate matches the role
- gap_severity: critical, high, medium, low
- priority: 1 (most important) to N (least important)
- candidate_level: none, beginner, basic, intermediate, advanced, expert
- strong_matches: skills where candidate meets or exceeds requirements
- missing_skills: required skills with zero evidence in resume
- Be specific and actionable in reasons
- Return ONLY the JSON, nothing else"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=5000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )

    text_response = _extract_text_block(response.content)
    return _parse_json_response(text_response)


def generate_questionnaire(
    skill_gaps: Dict,
    resume_data: Dict,
    jd_data: Dict
) -> List[Dict]:
    """
    Generate an adaptive MCQ questionnaire of 35-40 questions covering all skill gaps.
    Questions are distributed across basic/intermediate/advanced levels per skill.
    Uses adaptive thinking for balanced, high-quality question generation.

    Returns list of MCQ dicts:
        [{id, skill, level, question, options {A/B/C/D}, correct_answer, explanation, concept}]
    """
    gaps = skill_gaps.get("skill_gaps", [])
    missing = skill_gaps.get("missing_skills", [])

    # Build a combined skills list with context
    skills_to_assess = []
    for gap in gaps:
        skills_to_assess.append({
            "skill": gap["skill"],
            "candidate_level": gap["candidate_level"],
            "required_level": gap["required_level"],
            "gap_severity": gap["gap_severity"]
        })
    for skill in missing:
        skills_to_assess.append({
            "skill": skill,
            "candidate_level": "none",
            "required_level": "intermediate",
            "gap_severity": "high"
        })

    prompt = f"""You are an expert technical interviewer and assessment designer. Create a comprehensive adaptive questionnaire.

CANDIDATE BACKGROUND:
- Name: {resume_data.get('candidate_name', 'Candidate')}
- Experience: {resume_data.get('total_experience_years', 0)} years
- Current Skills: {[s['name'] for s in resume_data.get('skills', [])]}

SKILLS TO ASSESS:
{json.dumps(skills_to_assess, indent=2)}

JOB ROLE: {jd_data.get('role_title', 'Software Engineer')}

Generate exactly 37 multiple choice questions (35-40 range). Distribute questions across skills proportionally based on gap_severity (critical/high gaps get more questions). For each skill, create questions at basic, intermediate, and advanced levels.

Return ONLY a valid JSON array with this exact structure:
[
    {{
        "id": 1,
        "skill": "Machine Learning",
        "level": "basic",
        "question": "What is the primary difference between supervised and unsupervised learning?",
        "options": {{
            "A": "Supervised learning uses labeled data; unsupervised learning finds patterns in unlabeled data",
            "B": "Supervised learning is faster than unsupervised learning",
            "C": "Supervised learning requires more data than unsupervised learning",
            "D": "Supervised learning is only used for classification tasks"
        }},
        "correct_answer": "A",
        "explanation": "Supervised learning trains on labeled input-output pairs, while unsupervised learning discovers hidden structure in data without labels.",
        "concept": "Fundamental ML paradigms"
    }},
    {{
        "id": 2,
        "skill": "Machine Learning",
        "level": "intermediate",
        "question": "Which technique helps prevent overfitting in neural networks?",
        "options": {{
            "A": "Increasing learning rate",
            "B": "Dropout regularization",
            "C": "Adding more hidden layers",
            "D": "Removing validation set"
        }},
        "correct_answer": "B",
        "explanation": "Dropout randomly sets neurons to zero during training, preventing the network from over-relying on specific neurons and improving generalization.",
        "concept": "Regularization techniques"
    }}
]

Rules:
- id must be sequential integers starting from 1
- level must be: basic, intermediate, or advanced
- Each skill should have at least 3 questions (1 basic, 1 intermediate, 1 advanced)
- High/critical severity skills should get 5-7 questions
- All 4 options must be plausible (avoid obviously wrong answers)
- correct_answer must be exactly "A", "B", "C", or "D"
- questions must test practical knowledge, not just definitions
- Make questions relevant to real-world {jd_data.get('role_title', 'software engineering')} scenarios
- Return ONLY the JSON array, nothing else"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )

    text_response = _extract_text_block(response.content)
    questions = _parse_json_response(text_response)

    # Validate and normalize
    if not isinstance(questions, list):
        raise ValueError("Expected a list of questions from Claude")

    for i, q in enumerate(questions):
        q["id"] = i + 1  # Ensure sequential IDs

    return questions


def calculate_proficiency_scores(
    questions: List[Dict],
    answers: Dict[str, str]
) -> Dict[str, Dict]:
    """
    Calculate per-skill proficiency scores based on questionnaire answers.
    Pure Python calculation - no Claude call needed here.

    Args:
        questions: list of MCQ dicts with skill, level, correct_answer
        answers: dict mapping str(question_id) to chosen letter (A/B/C/D)

    Returns:
        {
            "Python": {
                "level": "intermediate",
                "score": 67,
                "details": {
                    "basic_accuracy": 100,
                    "intermediate_accuracy": 50,
                    "advanced_accuracy": 33
                }
            }
        }
    """
    # Group questions by skill and level
    skill_data = {}
    for q in questions:
        skill = q["skill"]
        level = q["level"]
        q_id = str(q["id"])

        if skill not in skill_data:
            skill_data[skill] = {
                "basic": {"correct": 0, "total": 0},
                "intermediate": {"correct": 0, "total": 0},
                "advanced": {"correct": 0, "total": 0}
            }

        skill_data[skill][level]["total"] += 1
        if answers.get(q_id) == q.get("correct_answer"):
            skill_data[skill][level]["correct"] += 1

    # Calculate scores per skill
    proficiency_scores = {}
    for skill, levels in skill_data.items():
        basic = levels["basic"]
        inter = levels["intermediate"]
        adv = levels["advanced"]

        # Calculate accuracy per level (0 if no questions at that level)
        def accuracy(data):
            if data["total"] == 0:
                return None
            return round((data["correct"] / data["total"]) * 100)

        basic_acc = accuracy(basic)
        inter_acc = accuracy(inter)
        adv_acc = accuracy(adv)

        # Overall score: weighted average (basic=1x, intermediate=2x, advanced=3x)
        total_weight = 0
        weighted_sum = 0
        if basic_acc is not None:
            weighted_sum += basic_acc * 1
            total_weight += 1
        if inter_acc is not None:
            weighted_sum += inter_acc * 2
            total_weight += 2
        if adv_acc is not None:
            weighted_sum += adv_acc * 3
            total_weight += 3

        overall_score = round(weighted_sum / total_weight) if total_weight > 0 else 0

        # Determine proficiency level from score
        if overall_score >= 85:
            level = "advanced"
        elif overall_score >= 65:
            level = "intermediate"
        elif overall_score >= 40:
            level = "basic"
        else:
            level = "beginner"

        proficiency_scores[skill] = {
            "level": level,
            "score": overall_score,
            "details": {
                "basic_accuracy": basic_acc if basic_acc is not None else 0,
                "intermediate_accuracy": inter_acc if inter_acc is not None else 0,
                "advanced_accuracy": adv_acc if adv_acc is not None else 0,
                "questions_attempted": basic["total"] + inter["total"] + adv["total"],
                "correct_answers": basic["correct"] + inter["correct"] + adv["correct"]
            }
        }

    return proficiency_scores


def generate_learning_pathway(
    proficiency_scores: Dict,
    skill_gaps: Dict,
    resume_data: Dict,
    jd_data: Dict
) -> Dict[str, Any]:
    """
    Generate a personalized learning pathway for all skill gaps.
    Uses adaptive thinking for a sophisticated, tailored plan.

    Returns comprehensive JSON with learning order, resources, timelines, etc.
    """
    prompt = f"""You are an expert learning and development specialist and curriculum designer. Create a personalized learning pathway.

CANDIDATE: {resume_data.get('candidate_name', 'Candidate')} ({resume_data.get('total_experience_years', 0)} years experience)

PROFICIENCY ASSESSMENT RESULTS:
{json.dumps(proficiency_scores, indent=2)}

SKILL GAPS IDENTIFIED:
{json.dumps(skill_gaps.get('skill_gaps', []), indent=2)}

TARGET ROLE: {jd_data.get('role_title', 'Software Engineer')}

Design a comprehensive, personalized learning pathway. Return ONLY a valid JSON object:
{{
    "total_estimated_weeks": 16,
    "overview": "A 16-week intensive upskilling program focusing on ML engineering and cloud infrastructure, building from your strong Python foundation.",
    "learning_order": ["Python Advanced", "Machine Learning", "Docker", "Kubernetes", "AWS"],
    "skills": [
        {{
            "skill_name": "Machine Learning",
            "current_level": "basic",
            "target_level": "advanced",
            "priority": "critical",
            "estimated_weeks": 6,
            "reasoning": "Core requirement for the role; your Python skills provide an excellent foundation to build upon",
            "prerequisites": ["Python Advanced", "Statistics Basics"],
            "resources": [
                {{
                    "type": "course",
                    "title": "Machine Learning Specialization",
                    "provider": "Coursera (Andrew Ng)",
                    "url": "https://www.coursera.org/specializations/machine-learning-introduction",
                    "estimated_hours": 60,
                    "description": "Comprehensive ML foundations covering supervised, unsupervised, and reinforcement learning"
                }},
                {{
                    "type": "book",
                    "title": "Hands-On Machine Learning with Scikit-Learn, Keras & TensorFlow",
                    "provider": "O'Reilly",
                    "url": "https://www.oreilly.com/library/view/hands-on-machine-learning/9781492032632/",
                    "estimated_hours": 40,
                    "description": "Practical guide with real-world projects and implementations"
                }},
                {{
                    "type": "practice",
                    "title": "Kaggle ML Competitions",
                    "provider": "Kaggle",
                    "url": "https://www.kaggle.com/competitions",
                    "estimated_hours": 20,
                    "description": "Apply skills on real datasets and compete with ML practitioners"
                }}
            ],
            "learning_steps": [
                {{
                    "week": 1,
                    "focus": "ML Fundamentals & Math Review",
                    "tasks": [
                        "Complete Andrew Ng's ML course Week 1-2",
                        "Review linear algebra and calculus basics",
                        "Implement linear regression from scratch in Python"
                    ],
                    "milestone": "Understand and implement basic regression models"
                }},
                {{
                    "week": 2,
                    "focus": "Classification & Model Evaluation",
                    "tasks": [
                        "Study decision trees and SVMs",
                        "Learn cross-validation and metrics (precision, recall, F1)",
                        "Complete first Kaggle competition submission"
                    ],
                    "milestone": "Build and evaluate a classification pipeline"
                }}
            ],
            "practice_project": "Build an end-to-end ML pipeline: data ingestion → feature engineering → model training → evaluation → FastAPI serving endpoint"
        }}
    ]
}}

Rules:
- Create an entry for EVERY skill in the skill_gaps list
- learning_order should sequence skills optimally (foundational skills first)
- priority: critical, high, medium, low (based on gap_severity and job requirements)
- resources: include 3-5 diverse resources per skill (courses, books, docs, practice platforms, videos)
- Use real, verified resources with accurate URLs
- learning_steps: provide week-by-week breakdown for each skill
- practice_project: suggest a hands-on project that demonstrates the skill
- estimated_weeks should be realistic and account for the gap severity
- Return ONLY the JSON, nothing else"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )

    text_response = _extract_text_block(response.content)
    return _parse_json_response(text_response)


def generate_skill_test(skill_name: str, target_level: str) -> List[Dict]:
    """
    Generate 8 verification MCQs for a specific skill at the target proficiency level.
    Uses adaptive thinking to ensure quality and appropriate difficulty.

    Returns list of 8 MCQ dicts:
        [{id, question, options {A/B/C/D}, correct_answer, explanation, concept_tested}]
    """
    prompt = f"""You are an expert technical examiner. Create a rigorous verification test for the skill: {skill_name}

TARGET PROFICIENCY LEVEL: {target_level}

Generate exactly 8 multiple choice questions that verify {target_level}-level competency in {skill_name}.
Questions should progressively increase in difficulty within the {target_level} range.

Return ONLY a valid JSON array:
[
    {{
        "id": 1,
        "question": "You have a dataset with 1 million rows and 500 features. Many features are highly correlated. Which dimensionality reduction technique would be most appropriate as a preprocessing step before training an SVM classifier?",
        "options": {{
            "A": "Feature selection using chi-squared test",
            "B": "Principal Component Analysis (PCA) to reduce to top 50 components",
            "C": "Random feature sampling",
            "D": "One-hot encoding all features"
        }},
        "correct_answer": "B",
        "explanation": "PCA is ideal here: it handles correlated features by transforming them into uncorrelated principal components, dramatically reducing dimensionality while preserving maximum variance. SVMs are particularly sensitive to high-dimensional sparse spaces, making PCA preprocessing critical for performance.",
        "concept_tested": "Dimensionality reduction and preprocessing for SVMs"
    }}
]

Rules:
- All 8 questions must test {target_level}-level knowledge of {skill_name}
- Questions should test PRACTICAL application, not just memorization
- Include scenario-based questions where appropriate
- All 4 options must be plausible to an intermediate learner
- correct_answer must be exactly "A", "B", "C", or "D"
- explanations must be detailed and educational (explain WHY the answer is correct)
- concept_tested should identify the specific sub-topic or concept
- Return ONLY the JSON array, nothing else"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    )

    text_response = _extract_text_block(response.content)
    questions = _parse_json_response(text_response)

    if not isinstance(questions, list):
        raise ValueError("Expected a list of questions")

    # Ensure sequential IDs
    for i, q in enumerate(questions):
        q["id"] = i + 1

    return questions[:8]  # Ensure exactly 8


def evaluate_skill_test(
    skill_name: str,
    questions: List[Dict],
    answers: Dict[str, str],
    target_level: str
) -> Dict[str, Any]:
    """
    Evaluate a completed skill test and generate detailed feedback using Claude.

    Args:
        skill_name: name of the skill being tested
        questions: the 8 MCQ dicts
        answers: {str(question_id): letter} mapping
        target_level: the target proficiency level

    Returns:
        {
            score: float (0-100),
            correct: int,
            total: int,
            passed: bool (score >= 75),
            wrong_answers: [{question, your_answer, correct_answer, explanation}],
            feedback: str,
            areas_to_review: [str]
        }
    """
    # Calculate score
    correct_count = 0
    wrong_answers = []

    for q in questions:
        q_id = str(q["id"])
        user_answer = answers.get(q_id, "")
        correct = q.get("correct_answer", "")

        if user_answer == correct:
            correct_count += 1
        else:
            wrong_answers.append({
                "question": q["question"],
                "your_answer": f"{user_answer}. {q['options'].get(user_answer, 'No answer')}",
                "correct_answer": f"{correct}. {q['options'].get(correct, '')}",
                "explanation": q.get("explanation", ""),
                "concept": q.get("concept_tested", "")
            })

    total = len(questions)
    score = round((correct_count / total) * 100) if total > 0 else 0
    passed = score >= 75

    # Extract areas to review from wrong answers
    areas_to_review = list(set(
        wa.get("concept", "") for wa in wrong_answers if wa.get("concept")
    ))

    # Generate personalized feedback with Claude
    performance_context = {
        "skill": skill_name,
        "target_level": target_level,
        "score": score,
        "correct": correct_count,
        "total": total,
        "passed": passed,
        "wrong_concepts": areas_to_review
    }

    feedback_prompt = f"""You are an expert learning coach. A candidate just completed a verification test.

TEST RESULTS:
- Skill: {skill_name}
- Target Level: {target_level}
- Score: {score}% ({correct_count}/{total} correct)
- Status: {"PASSED" if passed else "FAILED"}
- Areas needing improvement: {areas_to_review}

Write a brief, encouraging, and actionable feedback message (3-5 sentences) that:
1. Acknowledges their performance specifically
2. If passed: celebrates achievement and suggests next steps
3. If failed: identifies what to focus on and how to improve
4. Is warm, professional, and motivating

Return ONLY the feedback text, no JSON, no formatting."""

    feedback_response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": feedback_prompt}]
    )

    feedback_text = _extract_text_block(feedback_response.content).strip()

    return {
        "score": score,
        "correct": correct_count,
        "total": total,
        "passed": passed,
        "wrong_answers": wrong_answers,
        "feedback": feedback_text,
        "areas_to_review": areas_to_review
    }
