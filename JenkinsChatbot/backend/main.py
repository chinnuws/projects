import os
import logging
from dotenv import load_dotenv

# Load environment variables at the very beginning
load_dotenv()

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from config_loader import load_jobs_config, get_job_by_name
from ai_service import AIService
from jenkins_service import JenkinsService

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JenkinsBot")

app = FastAPI(title="Context-Aware Jenkins Bot", description="AI-powered interface for Jenkins.")

# CORS Handling
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
# We initialize inside startup event or globally if they are stateless enough.
# Here global is fine for simplicity.
ai_service = AIService()
jenkins_service = JenkinsService()
jobs_config = load_jobs_config()

class QueryRequest(BaseModel):
    text: str
    context: Optional[Dict[str, Any]] = {} # Previous conversation context if any

class QueryResponse(BaseModel):
    response_text: str
    intent: str
    job_name: Optional[str] = None
    potential_jobs: Optional[List[str]] = None
    parameters: Optional[Dict[str, Any]] = None
    missing_parameters: Optional[List[str]] = None
    action_required: str # "NONE", "CONFIRM_TRIGGER", "PROVIDE_PARAMS", "SHOW_STATUS", "AMBIGUOUS_JOB"
    job_doc_url: Optional[str] = None
    job_status: Optional[Dict[str, Any]] = None

@app.get("/jobs")
def get_jobs():
    """List all available jobs."""
    return jobs_config

@app.post("/chat", response_model=QueryResponse)
async def chat_interaction(request: QueryRequest):
    """
    Main interaction point. 
    1. AI analyzes text.
    2. Backend validates against job config.
    3. Returns appropriate action (ask for params, trigger job, show status).
    """
    user_text = request.text
    context = request.context or {}
    
    # 1. AI Analysis
    ai_result = ai_service.parse_input(user_text)
    
    intent = ai_result.get("intent", "UNKNOWN")
    job_name = ai_result.get("job_name")
    potential_jobs = ai_result.get("potential_jobs")
    extracted_params = ai_result.get("parameters", {})
    
    # Handle Ambiguity
    if potential_jobs and len(potential_jobs) > 1:
        jobs_list = " or ".join([f"'{j}'" for j in potential_jobs])
        return QueryResponse(
            response_text=f"I found multiple jobs matching your request. Did you mean {jobs_list}?",
            intent=intent,
            potential_jobs=potential_jobs,
            action_required="AMBIGUOUS_JOB"
        )

    # Intent & Job Recovery from Context
    # If the current message doesn't specify a job or intent, inherit from context
    if not job_name and context.get("current_job"):
        job_name = context.get("current_job")
    
    if intent == "UNKNOWN" and context.get("intent"):
        intent = context.get("intent")
    elif intent == "UNKNOWN" and job_name:
        # If we have a job but no intent, assume we are in the middle of a flow
        # Check context for what we were doing
        intent = context.get("intent", "TRIGGER") 
        
    # If we still don't know the job, but intent is explicit (e.g. "Trigger job"), ask which one.
    if intent == "TRIGGER" and not job_name:
        return QueryResponse(
            response_text="Which job would you like to trigger? Please specify the job name.",
            intent="TRIGGER",
            action_required="ASK_JOB_NAME"
        )
        
    if intent == "STATUS" and not job_name:
         return QueryResponse(
            response_text="Which job's status would you like to check?",
            intent="STATUS",
            action_required="ASK_JOB_NAME"
        )

    if job_name:
        job_config = get_job_by_name(job_name, jobs_config)
        if not job_config:
            return QueryResponse(
                response_text=f"I identified the job '{job_name}' but it's not in my configuration.",
                intent="UNKNOWN",
                action_required="NONE"
            )

        # 2. Validation
        if intent == "TRIGGER":
            required_params = [p['name'] for p in job_config['parameters'] if p.get('required', True)]
            missing = []
            
            # Merge extracted params with context params
            current_params = context.get("parameters", {})
            current_params.update(extracted_params)
            
            for req in required_params:
                if req not in current_params and req not in extracted_params:
                    # Check if present in input string directly via heuristics or just ask
                     missing.append(req)
            
            if missing:
                return QueryResponse(
                    response_text=f"I need more information to trigger '{job_name}'. Please provide: {', '.join(missing)}.",
                    intent="TRIGGER",
                    job_name=job_name,
                    parameters=current_params,
                    missing_parameters=missing,
                    action_required="PROVIDE_PARAMS",
                    job_doc_url=job_config.get("documentation_url")
                )
            else:
                # All params present -> Ask for confirmation
                return QueryResponse(
                    response_text=f"I have all the details to trigger '{job_name}'. Please confirm:",
                    intent="TRIGGER",
                    job_name=job_name,
                    parameters=current_params,
                    action_required="CONFIRM_TRIGGER"
                )

        elif intent == "STATUS":
            # Merge parameters from context
            current_params = context.get("parameters", {})
            current_params.update(extracted_params)
            
            build_number = current_params.get("BUILD_NUMBER")
            
            if not build_number:
                return QueryResponse(
                    response_text=f"Please provide the build number for '{job_name}' to check its status.",
                    intent="STATUS",
                    job_name=job_name,
                    parameters=current_params,
                    missing_parameters=["BUILD_NUMBER"],
                    action_required="PROVIDE_PARAMS"
                )

            # Use the job_path from config for Jenkins communication
            target_job = job_config.get('job_path', job_name)
            status = jenkins_service.get_job_status(target_job, build_number=int(build_number))
            return QueryResponse(
                response_text=f"Status for '{job_name}' build #{build_number}: {status.get('result', 'UNKNOWN')}",
                intent="STATUS",
                job_name=job_name,
                job_status=status,
                action_required="SHOW_STATUS"
            )

    # Fallback
    return QueryResponse(
        response_text="I'm not sure what you want to do. You can ask me to trigger a job or check its status.",
        intent="UNKNOWN",
        action_required="NONE"
    )

class TriggerRequest(BaseModel):
    job_name: str
    params: Dict[str, Any]

@app.post("/trigger")
async def trigger_job_endpoint(req: TriggerRequest):
    """Direct trigger endpoint."""
    # We need the job_path here too
    job_config = get_job_by_name(req.job_name, jobs_config)
    target_job = job_config.get('job_path', req.job_name) if job_config else req.job_name
    return jenkins_service.trigger_job(target_job, req.params)

@app.get("/queue/{item_id}")
async def get_queue_status(item_id: int):
    """Check if a queue item has turned into a build."""
    return jenkins_service.get_build_from_queue(item_id)

@app.get("/job/{job_name}/build/{build_number}")
async def get_specific_build_status(job_name: str, build_number: int):
    """Check status of a specific build."""
    # Need to resolve job_path
    job_config = get_job_by_name(job_name, jobs_config)
    target_job = job_config.get('job_path', job_name) if job_config else job_name
    return jenkins_service.get_job_status(target_job, build_number)
