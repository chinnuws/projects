# backend/main.py
from fastapi import FastAPI
from nlp import extract_intent
from job_router import find_job
from jenkins import trigger_jenkins

app = FastAPI()

@app.post("/process")
def process_query(payload: dict):
    user_input = payload["query"]
    params = payload.get("params", {})

    intent_data = extract_intent(user_input)
    job_name, job = find_job(intent_data["intent"], intent_data["resource"])

    if not job:
        return {"error": "No matching job found"}

    missing = [
        p for p in job["parameters"]
        if p["name"] not in params
    ]

    if missing:
        return {
            "status": "need_params",
            "missing": missing,
            "job": job_name
        }

    success = trigger_jenkins(job["url"], params)

    return {
        "status": "triggered",
        "success": success,
        "documentation": job["documentation"]
    }
