import os
import jenkins
import time
import logging

logger = logging.getLogger(__name__)

class JenkinsService:
    def __init__(self):
        self.url = os.getenv("JENKINS_URL", "http://localhost:8080")
        self.user = os.getenv("JENKINS_USER", "admin")
        self.token = os.getenv("JENKINS_TOKEN", "token")
        self.mock_mode = os.getenv("MOCK_JENKINS", "true").lower() == "true"
        
        self.server = None
        if not self.mock_mode:
            try:
                self.server = jenkins.Jenkins(self.url, username=self.user, password=self.token)
            except Exception as e:
                logger.error(f"Failed to connect to Jenkins: {e}")
                self.mock_mode = True

    def get_job_status(self, job_name: str, build_number: int = None):
        if self.mock_mode:
            # If build_number is 102 (our mock trigger build), check how long since "start"
            # Since we are stateless, we will just simulate a success after a few seconds
            # if the build_number matches our triggered one.
            return {
                "status": "SUCCESS",
                "full_name": job_name,
                "number": build_number or 101,
                "timestamp": int(time.time() * 1000),
                "result": "SUCCESS" if build_number != 102 or int(time.time()) % 15 > 10 else None,
                "duration": 5000,
                "url": f"{self.url}/job/{job_name}/{build_number or 101}/"
            }
        
        # Real implementation
        try:
            if build_number:
                info = self.server.get_build_info(job_name, build_number)
                return info
            else:
                info = self.server.get_job_info(job_name)
                last_build = info.get('lastBuild')
                if last_build:
                    return self.server.get_build_info(job_name, last_build['number'])
                return {"status": "NO_BUILDS", "url": f"{self.url}/job/{job_name}"}
        except Exception as e:
            logger.error(f"Error fetching job status: {e}")
            return {"error": str(e)}

    def get_build_from_queue(self, queue_item_id: int):
        if self.mock_mode:
            # item_id is a timestamp. If > 2 seconds have passed, it's "started"
            elapsed = int(time.time()) - queue_item_id
            if elapsed > 2:
                return {"build_number": 102, "status": "STARTED"}
            return {"status": "QUEUED"}

    def trigger_job(self, job_name: str, parameters: dict):
        if self.mock_mode:
            logger.info(f"Mock triggering job {job_name} with params {parameters}")
            return {
                "triggered": True,
                "queue_item": int(time.time()), # Using timestamp as mock queue ID
                "message": f"Job '{job_name}' triggered successfully (Mock).",
                "job_url": f"{self.url}/job/{job_name}/"
            }

        try:
            queue_item = self.server.build_job(job_name, parameters=parameters)
            return {
                "triggered": True, 
                "queue_item": queue_item,
                "message": f"Job '{job_name}' triggered successfully.",
                "job_url": f"{self.url}/job/{job_name}/"
            }
        except Exception as e:
             logger.error(f"Error triggering job: {e}")
             return {"triggered": False, "error": str(e)}
