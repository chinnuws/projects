import yaml
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "jobs.yaml")

def load_jobs_config():
    """Load job definitions from jobs.yaml."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}")
    
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)["jobs"]

def get_job_by_name(job_name: str, jobs: list):
    """Find a job definition by name."""
    for job in jobs:
        if job["name"].lower() == job_name.lower():
            return job
    return None
