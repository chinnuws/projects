import requests
import os
import time

JENKINS_URL = os.getenv("JENKINS_URL")
AUTH = (os.getenv("JENKINS_USER"), os.getenv("JENKINS_API_TOKEN"))


def trigger_jenkins(job_url, params):
    response = requests.post(
        f"{JENKINS_URL}{job_url}",
        auth=AUTH,
        params=params,
        allow_redirects=False
    )

    if response.status_code != 201:
        return None

    queue_url = response.headers.get("Location")
    return queue_url


def get_build_number(queue_url):
    while True:
        res = requests.get(f"{queue_url}api/json", auth=AUTH).json()
        if "executable" in res and res["executable"]:
            return res["executable"]["number"]
        time.sleep(2)


def get_build_status(job_name, build_number):
    url = f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json"
    res = requests.get(url, auth=AUTH).json()

    if res["building"]:
        return "RUNNING"
    return res["result"]

