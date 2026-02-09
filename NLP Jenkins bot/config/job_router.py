# backend/job_router.py
from config_loader import load_jobs

jobs = load_jobs()

def find_job(intent, resource):
    for job_name, job in jobs.items():
        if job["intent"] == intent and job["resource"] == resource:
            return job_name, job
    return None, None
