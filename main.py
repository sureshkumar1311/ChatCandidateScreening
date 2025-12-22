from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from models import (
    ChatRequest, ChatResponse, FinalReportRequest, 
    FinalReport, ParsedResume, ChatMessage
)
from services.resume_parser import resume_parser_service
from services.ai_agent import ai_agent_service
from services.database import database_service
from config import get_settings
import uvicorn

settings = get_settings()

app = FastAPI(
    title="AI Candidate Screening API",
    description="Chat-based AI screening system for candidates",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "AI Candidate Screening API",
        "version": "1.0.0"
    }

@app.post("/api/upload-resume", response_model=dict)
async def upload_resume(
    resume_file: UploadFile = File(...),
    job_description_file: UploadFile = File(default=None),
    job_description_text: Optional[str] = Form(default=None)
):
    """
    Endpoint 1: Upload resume and job description
    
    Job Description can be provided in TWO ways:
    1. As a file (PDF/DOCX) - upload via job_description_file
    2. As plain text - pass via job_description_text
    
    Returns parsed resume data and creates a new session
    """
    try:
        # Validate resume file type
        if not resume_file.filename.endswith(('.pdf', '.docx', '.doc')):
            raise HTTPException(
                status_code=400,
                detail="Resume must be PDF or DOCX format"
            )
        
        # Read and parse resume
        resume_bytes = await resume_file.read()
        parsed_resume = await resume_parser_service.parse_resume(
            resume_bytes, 
            resume_file.filename
        )
        
        # Process Job Description (File or Text)
        job_description = ""
        
        if job_description_file and job_description_file.filename:  # Added filename check
            # Option 1: Job Description as File
            if not job_description_file.filename.endswith(('.pdf', '.docx', '.doc', '.txt')):
                raise HTTPException(
                    status_code=400,
                    detail="Job description file must be PDF, DOCX, or TXT format"
                )
            
            jd_bytes = await job_description_file.read()
            
            # Handle TXT files
            if job_description_file.filename.endswith('.txt'):
                job_description = jd_bytes.decode('utf-8')
            else:
                # Parse PDF/DOCX
                job_description = await resume_parser_service.parse_job_description(
                    jd_bytes,
                    job_description_file.filename
                )
            
            print(f"✓ Job description parsed from file: {job_description_file.filename}")
            
        elif job_description_text:
            # Option 2: Job Description as Text
            job_description = job_description_text
            print(f"✓ Job description received as text ({len(job_description)} chars)")
            
        else:
            raise HTTPException(
                status_code=400,
                detail="Please provide job description either as file (job_description_file) or text (job_description_text)"
            )
        
        # Validate job description is not empty
        if not job_description or len(job_description.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Job description is too short or empty"
            )
        
        # Create new interview session
        session_id = database_service.create_session(
            candidate_name=parsed_resume.name,
            candidate_email=parsed_resume.email,
            resume_text=parsed_resume.raw_text,
            job_description=job_description
        )
        
        # Convert parsed_resume to dict with JSON-safe datetime serialization
        parsed_resume_dict = parsed_resume.model_dump()
        
        return {
            "success": True,
            "session_id": session_id,
            "parsed_resume": parsed_resume_dict,
            "job_description_preview": job_description[:200] + "..." if len(job_description) > 200 else job_description,
            "job_description_length": len(job_description),
            "message": "Resume and job description processed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint 2: Chat endpoint for interview conversation
    Handles back-and-forth Q&A between AI and candidate
    
    Only requires:
    - session_id: To identify the session
    - user_message: The candidate's response
    
    Resume and JD are fetched from the database automatically.
    """
    try:
        # Get session from database
        session = database_service.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if interview is already complete
        if session.is_complete:
            raise HTTPException(
                status_code=400,
                detail="Interview already completed. Please request final report."
            )
        
        # Add user message to history
        user_message = ChatMessage(
            sender="Candidate",
            text=request.user_message
        )
        session.messages.append(user_message)
        
        # Get AI response using data from session (no need to pass resume/JD)
        ai_reply = await ai_agent_service.get_next_question(
            resume=session.resume_text,
            job_description=session.job_description,
            conversation_history=session.messages,
            question_number=session.question_count
        )
        
        # Add AI message to history
        ai_message = ChatMessage(
            sender="AI",
            text=ai_reply
        )
        session.messages.append(ai_message)
        
        # Update question count
        session.question_count += 1
        
        # Check if interview is complete (10 questions asked - including closing message)
        is_complete = session.question_count >= 10
        
        # Update session in database
        database_service.update_session(
            session_id=request.session_id,
            messages=session.messages,
            question_count=session.question_count,
            is_complete=is_complete
        )
        
        return ChatResponse(
            ai_reply=ai_reply,
            session_id=request.session_id,
            question_number=session.question_count,
            is_complete=is_complete
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")
        
@app.post("/api/final-report", response_model=FinalReport)
async def generate_final_report(request: FinalReportRequest):
    """
    Endpoint 3: Generate final evaluation report
    
    Can be called:
    1. After interview is complete (10 questions answered) - Full evaluation
    2. During interview (early generation) - Partial evaluation with note
    
    Only requires:
    - session_id: To identify the session
    
    Resume, JD, and conversation history are fetched from the database automatically.
    """
    try:
        # Get session from database
        session = database_service.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if at least some questions were answered (minimum 3 for meaningful evaluation)
        if session.question_count < 3:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough data for evaluation. Only {session.question_count}/10 questions answered. Please answer at least 3 questions."
            )
        
        # Check if report already exists
        existing_report = database_service.get_report(request.session_id)
        if existing_report:
            return existing_report
        
        # Generate report using data from session
        # Pass questions_answered to inform AI about interview completion status
        report = await ai_agent_service.generate_final_report(
            candidate_name=session.candidate_name,
            resume=session.resume_text,
            job_description=session.job_description,
            conversation_history=session.messages,
            questions_answered=session.question_count  # NEW: Pass completion status
        )
        
        # Set session_id
        report.session_id = request.session_id
        
        # Save report to database
        database_service.save_report(report)
        
        # Optionally mark session as complete if not already
        if not session.is_complete:
            database_service.update_session(
                session_id=request.session_id,
                messages=session.messages,
                question_count=session.question_count,
                is_complete=True  # Mark as complete when report is generated
            )
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")
        
@app.get("/api/report/{session_id}", response_model=FinalReport)
async def get_report(session_id: str):
    """Get existing report by session ID"""
    report = database_service.get_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    session = database_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()

@app.get("/api/reports")
async def list_reports(limit: int = 50):
    """List all reports (for recruiter dashboard)"""
    reports = database_service.list_all_reports(limit=limit)
    return {"reports": [r.model_dump() for r in reports]}

if __name__ == "__main__":
    uvicorn.run('main:app', host="0.0.0.0", port=8000, reload=True)