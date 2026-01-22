from openai import AzureOpenAI
from config import get_settings
from models import MCQQuestion, MCQOption, MCQAnswer, MCQEvaluationReport
from typing import List, Dict, Any
import json
from datetime import datetime

settings = get_settings()

class MCQAgentService:
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version
        )
    
    async def generate_mcq_questions(
        self,
        resume: str,
        job_description: str,
        count: int = 5
    ) -> List[Dict[str, Any]]:
        """Generate MCQ questions based on resume and JD"""
        
        prompt = f"""
You are an expert technical recruiter creating cognitive aptitude assessment questions.

Based on the candidate's resume and job description, generate {count} multiple-choice questions that test:
1. Logical Reasoning (1-2 questions)
2. Technical Aptitude relevant to the JD (2-3 questions)
3. Problem Solving (1-2 questions)

CANDIDATE RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

Requirements:
- Each question should have 4 options (A, B, C, D)
- Questions should be relevant to the candidate's background and the job role
- Mix difficulty levels (medium to challenging)
- Include practical scenarios when possible
- Make questions thought-provoking and realistic

Return ONLY valid JSON in this exact format:
{{
  "questions": [
    {{
      "question_number": 1,
      "category": "Logical Reasoning",
      "question_text": "If all A are B, and some B are C, which statement must be true?",
      "options": [
        {{"option": "A", "text": "All A are C"}},
        {{"option": "B", "text": "Some A are C"}},
        {{"option": "C", "text": "No A are C"}},
        {{"option": "D", "text": "Cannot be determined"}}
      ],
      "correct_option": "D",
      "explanation": "Detailed explanation of why D is correct..."
    }}
  ]
}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": "You are an expert at creating cognitive aptitude assessments. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=3000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Clean markdown formatting
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.rsplit('```', 1)[0]
            
            parsed = json.loads(result_text)
            return parsed['questions']
            
        except Exception as e:
            print(f"MCQ generation error: {e}")
            raise Exception(f"Failed to generate MCQ questions: {str(e)}")
    
    async def evaluate_answer(
        self,
        question_data: Dict[str, Any],
        selected_option: str
    ) -> MCQAnswer:
        """Evaluate a single MCQ answer"""
        
        correct_option = question_data['correct_option']
        is_correct = selected_option.upper() == correct_option.upper()
        
        # Find selected option text
        selected_text = ""
        for opt in question_data['options']:
            if opt['option'].upper() == selected_option.upper():
                selected_text = opt['text']
                break
        
        return MCQAnswer(
            question_number=question_data['question_number'],
            question_text=question_data['question_text'],
            selected_option=selected_option.upper(),
            selected_text=selected_text,
            correct_option=correct_option.upper(),
            is_correct=is_correct,
            explanation=question_data['explanation']
        )
    
    async def generate_evaluation_report(
        self,
        candidate_name: str,
        resume: str,
        job_description: str,
        answers: List[MCQAnswer]
    ) -> MCQEvaluationReport:
        """Generate comprehensive MCQ evaluation report"""
        
        # Calculate scores
        total_questions = len(answers)
        correct_answers = sum(1 for ans in answers if ans.is_correct)
        score_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        # Calculate category-wise scores
        category_scores = {}
        for answer in answers:
            # Extract category from stored question data (you'll need to pass this)
            category = "General"  # Default category
            
            if category not in category_scores:
                category_scores[category] = {"correct": 0, "total": 0}
            
            category_scores[category]["total"] += 1
            if answer.is_correct:
                category_scores[category]["correct"] += 1
        
        # Format answers for AI analysis
        answers_summary = "\n\n".join([
            f"Q{ans.question_number}: {ans.question_text}\n"
            f"Selected: {ans.selected_option} - {ans.selected_text}\n"
            f"Correct: {ans.correct_option}\n"
            f"Result: {'✓ Correct' if ans.is_correct else '✗ Incorrect'}"
            for ans in answers
        ])
        
        # Generate AI assessment
        assessment_prompt = f"""
Based on the MCQ test results, provide a comprehensive assessment.

CANDIDATE: {candidate_name}

RESUME SUMMARY:
{resume[:500]}...

JOB DESCRIPTION SUMMARY:
{job_description[:500]}...

TEST RESULTS:
Score: {correct_answers}/{total_questions} ({score_percentage:.1f}%)

ANSWERS:
{answers_summary}

Provide:
1. Overall Assessment (2-3 sentences about cognitive abilities)
2. Cognitive Strengths (3-4 specific strengths observed)
3. Areas for Improvement (2-3 areas to work on)
4. Recommendation (whether to proceed to next round)

Return ONLY valid JSON:
{{
  "overall_assessment": "The candidate demonstrated...",
  "cognitive_strengths": ["Strong logical reasoning", "Good technical aptitude"],
  "areas_for_improvement": ["Speed in problem-solving", "Complex scenario analysis"],
  "recommendation": "Proceed to technical interview round"
}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": "You are an expert at evaluating cognitive aptitude assessments. Return only valid JSON."},
                    {"role": "user", "content": assessment_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Clean markdown formatting
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.rsplit('```', 1)[0]
            
            assessment = json.loads(result_text)
            
            return MCQEvaluationReport(
                session_id="",  # Will be set by caller
                candidate_name=candidate_name,
                total_questions=total_questions,
                correct_answers=correct_answers,
                score_percentage=score_percentage,
                category_scores=category_scores,
                answers=answers,
                overall_assessment=assessment['overall_assessment'],
                cognitive_strengths=assessment['cognitive_strengths'],
                areas_for_improvement=assessment['areas_for_improvement'],
                recommendation=assessment['recommendation']
            )
            
        except Exception as e:
            print(f"Evaluation report error: {e}")
            raise Exception(f"Failed to generate evaluation report: {str(e)}")

mcq_agent_service = MCQAgentService()