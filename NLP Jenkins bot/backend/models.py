from pydantic import BaseModel
from typing import Dict, Optional, List

class UserQuery(BaseModel):
    query: str
    params: Optional[Dict[str, str]] = {}

class MissingParam(BaseModel):
    name: str
    prompt: str

class JobResponse(BaseModel):
    status: str
    success: Optional[bool] = None
    missing: Optional[List[MissingParam]] = None
    documentation: Optional[str] = None
