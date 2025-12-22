from openai import AzureOpenAI
from config import get_settings
from models import ChatMessage, FinalReport, RecommendationType
from typing import List, Dict, Any
import json
from datetime import datetime

settings = get_settings()

class AIAgentService:
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version
        )
        
        self.system_prompt = """You are an AI Technical Recruiter conducting a candidate screening interview.

Your role:
1. Ask personalized interview questions based on the candidate's resume and job description
2. Ask ONE question at a time
3. Adapt follow-up questions based on previous answers
4. Be professional, friendly, and conversational
5. After 6 questions, you will provide a final evaluation

Interview Structure:
- Question 1: Ask about their most recent/relevant project
- Question 2: Validate key skills from their resume relevant to the JD
- Question 3: Technical challenge they solved
- Question 4: Team collaboration and communication
- Question 5: Problem-solving scenario
- Question 6: JD-specific technical question

Keep questions conversational and natural. Don't be too formal."""
    
    async def get_next_question(
        self, 
        resume: str, 
        job_description: str, 
        conversation_history: List[ChatMessage],
        question_number: int
    ) -> str:
        """Generate next interview question"""
        
        # Build conversation context
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": f"CANDIDATE RESUME:\n{resume}"},
            {"role": "system", "content": f"JOB DESCRIPTION:\n{job_description}"},
            {"role": "system", "content": f"Current Question Number: {question_number + 1}/6"}
        ]
        
        # Add conversation history
        for msg in conversation_history:
            role = "assistant" if msg.sender == "AI" else "user"
            messages.append({"role": role, "content": msg.text})
        
        # Add instruction for next question
        if question_number == 0:
            messages.append({
                "role": "user", 
                "content": "Start the interview with a warm greeting and ask the first question about their most recent project."
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Ask question {question_number + 1} based on the interview structure and their previous responses."
            })
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )
        
        return response.choices[0].message.content
    
    async def generate_final_report(
        self,
        candidate_name: str,
        resume: str,
        job_description: str,
        conversation_history: List[ChatMessage]
    ) -> FinalReport:
        """Generate comprehensive final evaluation report"""
        
        # Format conversation
        conversation_text = "\n\n".join([
            f"{msg.sender}: {msg.text}" for msg in conversation_history
        ])
        
        evaluation_prompt = f"""
Based on the complete interview, generate a detailed evaluation report.

CANDIDATE RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

INTERVIEW TRANSCRIPT:
{conversation_text}

Analyze and score the candidate on:
1. Skill Match (0-100): How well their skills align with job requirements
2. Experience Match (0-100): Relevance and depth of their experience
3. Communication (0-100): Clarity, articulation, and professionalism
4. Problem Solving (0-100): Analytical thinking and approach to challenges
5. Overall Fit (0-100): Composite score considering all factors

Also provide:
- Recommendation: "Strongly Recommended for Next Round", "Recommended for Next Round", "Maybe - Consider for Next Round", or "Not Recommended"
- Strengths: List 3-5 key strengths
- Weaknesses: List 2-4 areas of concern or gaps
- Detailed Feedback: 2-3 paragraph summary

Return ONLY valid JSON in this exact format:
{{
  "skill_match": 85,
  "experience_match": 78,
  "communication": 92,
  "problem_solving": 80,
  "overall_fit": 84,
  "recommendation": "Recommended for Next Round",
  "strengths": ["Strong React expertise", "Good problem-solving", "Clear communication"],
  "weaknesses": ["Limited cloud experience", "Needs more system design practice"],
  "detailed_feedback": "The candidate demonstrated..."
}}
"""
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": "You are an expert technical recruiter evaluating candidates. Return only valid JSON."},
                {"role": "user", "content": evaluation_prompt}
            ],
            temperature=0.2,
            max_tokens=1500
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Clean markdown formatting
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.rsplit('```', 1)[0]
        
        evaluation = json.loads(result_text)
        
        # Create FinalReport object
        report = FinalReport(
            session_id="",  # Will be set by caller
            candidate_name=candidate_name,
            skill_match=evaluation['skill_match'],
            experience_match=evaluation['experience_match'],
            communication=evaluation['communication'],
            problem_solving=evaluation['problem_solving'],
            overall_fit=evaluation['overall_fit'],
            recommendation=RecommendationType(evaluation['recommendation']),
            strengths=evaluation['strengths'],
            weaknesses=evaluation['weaknesses'],
            detailed_feedback=evaluation['detailed_feedback'],
            transcript=conversation_history,
            generated_at=datetime.utcnow()
        )
        
        return report

ai_agent_service = AIAgentService()