# backend/jenkins.py
import requests
import os

def trigger_jenkins(job_url, params):
    response = requests.post(
        f"{os.getenv('JENKINS_URL')}{job_url}",
        auth=(os.getenv("JENKINS_USER"), os.getenv("JENKINS_API_TOKEN")),
        params=params
    )
    return response.status_code == 201
