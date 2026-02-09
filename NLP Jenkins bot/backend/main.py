from fastapi import FastAPI
from models import UserQuery, JobResponse
from nlp import extract_intent
from job_router import find_job
from jenkins import trigger_jenkins

app = FastAPI(title="ChatOps Backend")

@app.post("/process", response_model=JobResponse)
def process_query(payload: UserQuery):
    intent_data = extract_intent(payload.query)
    job_name, job = find_job(intent_data["intent"], intent_data["resource"])

    if not job:
        return {"status": "error"}

    missing = [
        p for p in job["parameters"]
        if p["name"] not in payload.params
    ]

    if missing:
        return {
            "status": "need_params",
            "missing": missing
        }

    success = trigger_jenkins(job["url"], payload.params)

    return {
        "status": "triggered",
        "success": success,
        "documentation": job["documentation"]
    }
