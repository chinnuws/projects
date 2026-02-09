from fastapi import FastAPI
from models import UserQuery
from nlp import extract_intent
from job_router import find_job
from jenkins import trigger_jenkins, get_build_number, get_build_status

app = FastAPI(title="ChatOps Backend")

build_tracker = {}  # simple in-memory store


@app.post("/process")
def process_query(payload: UserQuery):
    intent_data = extract_intent(payload.query)
    job_name, job = find_job(intent_data["intent"], intent_data["resource"])

    if not job:
        return {"type": "bot", "message": "❌ No matching job found."}

    missing = [
        p for p in job["parameters"]
        if p["name"] not in payload.params
    ]

    if missing:
        return {
            "type": "params",
            "missing": missing,
            "job_name": job_name
        }

    queue_url = trigger_jenkins(job["url"], payload.params)
    if not queue_url:
        return {"type": "bot", "message": "❌ Failed to trigger Jenkins job."}

    build_number = get_build_number(queue_url)
    build_tracker[job_name] = build_number

    return {
        "type": "build_started",
        "job_name": job_name,
        "build_number": build_number
    }


@app.get("/status/{job_name}")
def poll_status(job_name: str):
    build_number = build_tracker.get(job_name)
    if not build_number:
        return {"status": "UNKNOWN"}

    status = get_build_status(job_name, build_number)
    return {"status": status}
