from fastapi import FastAPI
from dotenv import load_dotenv
from models import UserQuery
from nlp import extract_intent
from job_router import find_job
from jenkins import (
    trigger_jenkins,
    get_build_number,
    get_build_status
)

load_dotenv()

app = FastAPI(
    title="ChatOps Backend",
    description="Natural language to Jenkins job orchestrator",
    version="1.0.0"
)

# In-memory build tracking (dev/local)
# { job_name: build_number }
build_tracker = {}


@app.post("/process")
def process_query(payload: UserQuery):
    """
    1. Extract intent & resource using AI
    2. Find matching Jenkins job from config
    3. Ask for missing parameters OR
    4. Trigger Jenkins job
    """

    # ------------------ NLP ------------------
    intent_data = extract_intent(payload.query)
    intent = intent_data.get("intent")
    resource = intent_data.get("resource")

    if not intent or not resource:
        return {
            "type": "bot",
            "message": "❌ I couldn't understand the request. Please rephrase."
        }

    # ------------------ Job Mapping ------------------
    job_name, job = find_job(intent, resource)

    if not job:
        return {
            "type": "bot",
            "message": "❌ No matching Jenkins job found for this request."
        }

    # ------------------ Parameter Validation ------------------
    missing_params = [
        p for p in job["parameters"]
        if p["name"] not in payload.params
    ]

    if missing_params:
        return {
            "type": "params",
            "job_name": job_name,
            "missing": missing_params
        }

    # ------------------ Trigger Jenkins ------------------
    queue_url = trigger_jenkins(job["url"], payload.params)

    if not queue_url:
        return {
            "type": "bot",
            "message": "❌ Failed to trigger Jenkins job."
        }

    build_number = get_build_number(queue_url)

    build_tracker[job_name] = build_number

    return {
        "type": "build_started",
        "job_name": job_name,
        "build_number": build_number
    }


@app.get("/status/{job_name}")
def get_status(job_name: str):
    """
    Poll Jenkins for build status
    """
    build_number = build_tracker.get(job_name)

    if not build_number:
        return {"status": "UNKNOWN"}

    status = get_build_status(job_name, build_number)

    return {
        "status": status,
        "job_name": job_name,
        "build_number": build_number
    }
