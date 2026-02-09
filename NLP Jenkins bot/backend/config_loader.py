# backend/config_loader.py
import yaml

def load_jobs():
    with open("config/jobs.yaml") as f:
        return yaml.safe_load(f)["jobs"]
