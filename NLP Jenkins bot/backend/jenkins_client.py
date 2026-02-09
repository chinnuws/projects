import requests

JENKINS_USER = "admin"
JENKINS_TOKEN = "your_api_token"

def trigger_jenkins_job(job_url, params):
    response = requests.post(
        job_url,
        params=params,
        auth=(JENKINS_USER, JENKINS_TOKEN)
    )

    if response.status_code in [200, 201]:
        return True
    return False
