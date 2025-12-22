from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Request Models

class UploadResumeRequest(BaseModel):
    """Request model for upload endpoint when using JSON"""
    resume_text: Optional[str] = None
    job_description_text: Optional[str] = None
    
class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    # Removed resume, job_description, and state - not needed!

class FinalReportRequest(BaseModel):
    session_id: str
    # Removed job_description - not needed!

# Response Models
class ParsedExperience(BaseModel):
    company: str
    role: str
    dates: str
    description: Optional[str] = None

class ParsedResume(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    skills: List[str]
    education: List[str]
    experience: List[ParsedExperience]
    raw_text: str

class ChatMessage(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    sender: str
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatResponse(BaseModel):
    ai_reply: str
    session_id: str
    question_number: int
    is_complete: bool = False

class RecommendationType(str, Enum):
    STRONGLY_RECOMMENDED = "Strongly Recommended for Next Round"
    RECOMMENDED = "Recommended for Next Round"
    MAYBE = "Maybe - Consider for Next Round"
    NOT_RECOMMENDED = "Not Recommended"

class FinalReport(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    session_id: str
    candidate_name: str
    skill_match: int = Field(ge=0, le=100)
    experience_match: int = Field(ge=0, le=100)
    communication: int = Field(ge=0, le=100)
    problem_solving: int = Field(ge=0, le=100)
    overall_fit: int = Field(ge=0, le=100)
    recommendation: RecommendationType
    strengths: List[str]
    weaknesses: List[str]
    detailed_feedback: str
    transcript: List[ChatMessage]
    generated_at: datetime = Field(default_factory=datetime.utcnow)

# Database Models
class InterviewSession(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    id: str
    session_id: str
    candidate_name: str
    candidate_email: str
    resume_text: str
    job_description: str
    messages: List[ChatMessage] = []
    question_count: int = 0
    is_complete: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)