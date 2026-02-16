import os
import json
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from config_loader import load_jobs_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.endpoint = os.getenv("AZURE_AI_ENDPOINT", "https://your-resource.openai.azure.com/")
        self.api_key = os.getenv("AZURE_AI_KEY", "your-api-key")
        self.deployment_name = os.getenv("AZURE_AI_DEPLOYMENT", "gpt-4")
        
        self.jobs = load_jobs_config()
        self.client = None
        
        if self.api_key != "your-api-key":
             try:
                self.client = ChatCompletionsClient(
                    endpoint=self.endpoint,
                    credential=AzureKeyCredential(self.api_key)
                )
             except Exception as e:
                 logger.error(f"Failed to initialize Azure AI Client: {e}")

    def _get_system_prompt(self) -> str:
        jobs_summary = []
        for job in self.jobs:
            params = [p['name'] for p in job.get('parameters', [])]
            jobs_summary.append(f"- Name: {job['name']}, Description: {job['description']}, Params: {', '.join(params)}")
        
        jobs_text = "\n".join(jobs_summary)
        
        return f"""
You are an intelligent Jenkins assistant. Your goal is to understand user intent and extract relevant details for Jenkins jobs.

Available Jobs:
{jobs_text}

Task:
1. Analyze the user's input.
2. Determine the Intent: 'TRIGGER' (to start a job) or 'STATUS' (to check job status).
3. Identify the Job Name based on the available jobs list. 
4. If the input is ambiguous and could match multiple jobs, list all potential job names in the 'potential_jobs' array and set 'job_name' to null.
5. Extract any parameters provided in the input. Map them to the job's parameter names.
6. For 'STATUS' intent, look for build numbers (e.g., 'build 105', '#105', '105') and extract as 'BUILD_NUMBER'.
7. Note: If the user asks about a job not in the list, set Job Name to null.

Output JSON format ONLY:
{{
  "intent": "TRIGGER" | "STATUS" | "UNKNOWN",
  "job_name": "Exact Job Name" | null,
  "potential_jobs": ["Name 1", "Name 2"] | null,
  "parameters": {{ "PARAM_NAME": "extracted_value" }},
  "missing_info": "Description of what is missing if intent is clear but job is vague."
}}
"""

    def parse_input(self, user_text: str) -> Dict[str, Any]:
        """
        Parses the user input using Azure AI to determine intent and parameters.
        Falls back to basic keyword matching if AI service is unavailable.
        """
        if self.client:
            try:
                response = self.client.complete(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": user_text}
                    ],
                    model=self.deployment_name,
                    temperature=0.1, # Low temperature for deterministic output
                    max_tokens=500
                )
                content = response.choices[0].message.content.strip()
                # Clean up markdown code blocks if present
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                
                return json.loads(content)
            except Exception as e:
                logger.error(f"Azure AI call failed: {e}. Falling back to rule-based parsing.")
        
        # Fallback Logic (Mock AI)
        return self._fallback_parsing(user_text)

    def _fallback_parsing(self, text: str) -> Dict[str, Any]:
        """Simple rule-based parsing for demo purposes when no API key is set."""
        text_lower = text.lower()
        intent = "UNKNOWN"
        job_name = None
        potential_jobs = []
        params = {}
        
        if any(w in text_lower for w in ["create", "deploy", "trigger", "run", "start"]):
            intent = "TRIGGER"
        elif any(w in text_lower for w in ["status", "check", "how's", "result"]):
            intent = "STATUS"
            
        # Try to match job names
        matches = []
        for job in self.jobs:
            name = job['name']
            name_lower = name.lower()
            
            # 1. Exact or near exact match
            if name_lower == text_lower or name_lower in text_lower:
                matches.append((name, 100))
                continue
                
            # 2. Keyword overlap
            job_tokens = set(name_lower.split())
            text_tokens = set(text_lower.split())
            overlap = len(job_tokens.intersection(text_tokens))
            
            if overlap > 0:
                score = (overlap / len(job_tokens)) * 50 # Basic scoring
                matches.append((name, score))
        
        # Sort matches by score
        matches.sort(key=lambda x: x[1], reverse=True)
        
        if len(matches) == 1:
            job_name = matches[0][0]
        elif len(matches) > 1:
            # If top match is much better than others, pick it
            if matches[0][1] > matches[1][1] * 1.5:
                job_name = matches[0][0]
            else:
                # Ambigous
                potential_jobs = [m[0] for m in matches[:3]] # Top 3 potential
        
        # Attempt to extract common params based on simple heuristics
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in ["cluster", "in"]:
                if i + 1 < len(words):
                    params["CLUSTER_NAME"] = words[i+1]
            if word.lower() in ["namespace", "named"]:
                 if i + 1 < len(words):
                    params["NAMESPACE_NAME"] = words[i+1]
            if word.lower() == "build" or word.startswith("#"):
                val = words[i+1] if word.lower() == "build" and i+1 < len(words) else word.replace("#", "")
                if val.isdigit():
                    params["BUILD_NUMBER"] = val
        
        return {
            "intent": intent,
            "job_name": job_name,
            "potential_jobs": potential_jobs if not job_name else None,
            "parameters": params,
            "missing_info": "AI Service unavailable, using basic keyword matching." if not self.client else None
        }
