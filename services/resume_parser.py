from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from models import ParsedResume, ParsedExperience
from config import get_settings
import PyPDF2
import docx
import io
from typing import List

settings = get_settings()

class ResumeParserService:
    def __init__(self):
        self.client = DocumentAnalysisClient(
            endpoint=settings.azure_document_intelligence_endpoint,
            credential=AzureKeyCredential(settings.azure_document_intelligence_key)
        )
    
    def extract_text_from_pdf(self, file_bytes: bytes) -> str:
        """Fallback PDF text extraction"""
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"PDF extraction error: {e}")
            return ""
    
    def extract_text_from_docx(self, file_bytes: bytes) -> str:
        """Fallback DOCX text extraction"""
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([para.text for para in doc.paragraphs])
            return text
        except Exception as e:
            print(f"DOCX extraction error: {e}")
            return ""
    
    async def parse_resume(self, file_bytes: bytes, filename: str) -> ParsedResume:
        """Parse resume using Azure Document Intelligence"""
        try:
            # Try Azure Document Intelligence first
            poller = self.client.begin_analyze_document(
                "prebuilt-document",
                file_bytes
            )
            result = poller.result()
            
            # Extract text content
            raw_text = ""
            for page in result.pages:
                for line in page.lines:
                    raw_text += line.content + "\n"
            
            # Basic field extraction
            name = ""
            email = ""
            phone = ""
            skills = []
            education = []
            
            # Try to extract key-value pairs
            if hasattr(result, 'key_value_pairs'):
                for kv in result.key_value_pairs:
                    if kv.key and kv.value:
                        key_text = kv.key.content.lower()
                        value_text = kv.value.content
                        
                        if 'name' in key_text:
                            name = value_text
                        elif 'email' in key_text:
                            email = value_text
                        elif 'phone' in key_text or 'mobile' in key_text:
                            phone = value_text
            
            # If Document Intelligence doesn't extract well, use fallback
            if not raw_text:
                if filename.endswith('.pdf'):
                    raw_text = self.extract_text_from_pdf(file_bytes)
                elif filename.endswith('.docx'):
                    raw_text = self.extract_text_from_docx(file_bytes)
            
            # Use OpenAI to parse the resume text intelligently
            parsed_data = await self._parse_with_ai(raw_text)
            
            return ParsedResume(
                name=parsed_data.get('name', name or 'Unknown'),
                email=parsed_data.get('email', email or ''),
                phone=parsed_data.get('phone', phone),
                skills=parsed_data.get('skills', []),
                education=parsed_data.get('education', []),
                experience=parsed_data.get('experience', []),
                raw_text=raw_text
            )
            
        except Exception as e:
            print(f"Azure Document Intelligence error: {e}")
            # Fallback to simple text extraction
            raw_text = ""
            if filename.endswith('.pdf'):
                raw_text = self.extract_text_from_pdf(file_bytes)
            elif filename.endswith('.docx'):
                raw_text = self.extract_text_from_docx(file_bytes)
            
            if raw_text:
                parsed_data = await self._parse_with_ai(raw_text)
                return ParsedResume(
                    name=parsed_data.get('name', 'Unknown'),
                    email=parsed_data.get('email', ''),
                    phone=parsed_data.get('phone'),
                    skills=parsed_data.get('skills', []),
                    education=parsed_data.get('education', []),
                    experience=parsed_data.get('experience', []),
                    raw_text=raw_text
                )
            
            raise Exception("Failed to parse resume")
    
    async def _parse_with_ai(self, text: str) -> dict:
        """Use OpenAI to intelligently parse resume text"""
        from openai import AzureOpenAI
        
        client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version
        )
        
        prompt = f"""
Extract the following information from this resume text and return ONLY valid JSON:

{{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "skills": ["skill1", "skill2", ...],
  "education": ["degree/institution", ...],
  "experience": [
    {{
      "company": "company name",
      "role": "job title",
      "dates": "employment period",
      "description": "brief description"
    }}
  ]
}}

Resume Text:
{text}

Return ONLY the JSON, no other text.
"""
        
        try:
            response = client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a resume parser. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            import json
            result_text = response.choices[0].message.content.strip()
            # Remove markdown code blocks if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            
            parsed = json.loads(result_text)
            
            # Convert experience to ParsedExperience objects
            if 'experience' in parsed:
                parsed['experience'] = [
                    ParsedExperience(**exp) for exp in parsed['experience']
                ]
            
            return parsed
            
        except Exception as e:
            print(f"AI parsing error: {e}")
            return {
                "name": "Unknown",
                "email": "",
                "phone": "",
                "skills": [],
                "education": [],
                "experience": []
            }

    async def parse_job_description(self, file_bytes: bytes, filename: str) -> str:
        """Parse job description from PDF or DOCX file"""
        try:
            if filename.endswith('.pdf'):
                return self.extract_text_from_pdf(file_bytes)
            elif filename.endswith(('.docx', '.doc')):
                return self.extract_text_from_docx(file_bytes)
            else:
                raise ValueError(f"Unsupported file format: {filename}")
        except Exception as e:
            print(f"Job description parsing error: {e}")
            raise Exception(f"Failed to parse job description: {str(e)}")

resume_parser_service = ResumeParserService()