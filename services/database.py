from azure.cosmos import CosmosClient, PartitionKey, exceptions
from config import get_settings
from models import InterviewSession, ChatMessage, FinalReport
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

settings = get_settings()

def serialize_datetime(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively serialize datetime objects to ISO format strings for Cosmos DB"""
    if isinstance(obj, dict):
        return {k: serialize_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

class DatabaseService:
    def __init__(self):
        self.client = CosmosClient(
            url=settings.cosmos_uri,
            credential=settings.cosmos_key
        )
        self.database = self.client.get_database_client(settings.cosmos_database)
        
        # Initialize containers
        self._init_containers()
    
    def _init_containers(self):
        """Initialize Cosmos DB containers"""
        try:
            # Sessions container
            self.sessions_container = self.database.create_container_if_not_exists(
                id="sessions",
                partition_key=PartitionKey(path="/session_id"),
                offer_throughput=400
            )
            
            # Reports container
            self.reports_container = self.database.create_container_if_not_exists(
                id="reports",
                partition_key=PartitionKey(path="/session_id"),
                offer_throughput=400
            )
        except exceptions.CosmosHttpResponseError as e:
            print(f"Container initialization error: {e}")
    
    def create_session(
        self,
        candidate_name: str,
        candidate_email: str,
        resume_text: str,
        job_description: str
    ) -> str:
        """Create new interview session"""
        session_id = str(uuid.uuid4())
        
        session = InterviewSession(
            id=session_id,
            session_id=session_id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            resume_text=resume_text,
            job_description=job_description,
            messages=[],
            question_count=0,
            is_complete=False
        )
        
        # Convert to dict with proper datetime serialization
        session_dict = session.model_dump(mode='json')  # Changed this line
        
        self.sessions_container.create_item(body=session_dict)
        return session_id
    
    def get_session(self, session_id: str) -> Optional[InterviewSession]:
        """Retrieve session by ID"""
        try:
            item = self.sessions_container.read_item(
                item=session_id,
                partition_key=session_id
            )
            return InterviewSession(**item)
        except exceptions.CosmosResourceNotFoundError:
            return None
    
    def update_session(
        self,
        session_id: str,
        messages: List[ChatMessage],
        question_count: int,
        is_complete: bool = False
    ):
        """Update session with new messages"""
        try:
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            
            session.messages = messages
            session.question_count = question_count
            session.is_complete = is_complete
            
            from datetime import datetime
            session.updated_at = datetime.utcnow()
            
            # Convert to dict with proper datetime serialization
            session_dict = session.model_dump(mode='json')  # Changed this line
            
            self.sessions_container.upsert_item(body=session_dict)
        except Exception as e:
            print(f"Session update error: {e}")
            raise
    
    def save_report(self, report: FinalReport):
        """Save final evaluation report"""
        try:
            # Convert to dict with proper datetime serialization
            report_dict = report.model_dump(mode='json')  # Changed this line
            report_dict['id'] = report.session_id
            
            self.reports_container.upsert_item(body=report_dict)
        except Exception as e:
            print(f"Report save error: {e}")
            raise
    
    def get_report(self, session_id: str) -> Optional[FinalReport]:
        """Retrieve report by session ID"""
        try:
            item = self.reports_container.read_item(
                item=session_id,
                partition_key=session_id
            )
            return FinalReport(**item)
        except exceptions.CosmosResourceNotFoundError:
            return None
    
    def list_all_reports(self, limit: int = 50) -> List[FinalReport]:
        """List all reports"""
        try:
            query = f"SELECT * FROM c ORDER BY c.generated_at DESC OFFSET 0 LIMIT {limit}"
            items = list(self.reports_container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
            return [FinalReport(**item) for item in items]
        except Exception as e:
            print(f"List reports error: {e}")
            return []
        
    # Add these methods to the DatabaseService class

    def create_mcq_session(
        self,
        candidate_name: str,
        candidate_email: str,
        resume_text: str,
        job_description: str,
        questions: List[Dict[str, Any]]
    ) -> str:
        """Create new MCQ session"""
        session_id = str(uuid.uuid4())
        
        from models import MCQSession
        session = MCQSession(
            id=session_id,
            session_id=session_id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            resume_text=resume_text,
            job_description=job_description,
            questions=questions,
            answers=[],
            current_question_number=0,
            is_complete=False
        )
        
        # Convert to dict and serialize datetime objects
        session_dict = session.model_dump()
        session_dict = serialize_datetime(session_dict)
        
        # Create MCQ sessions container if not exists
        try:
            self.mcq_sessions_container = self.database.create_container_if_not_exists(
                id="mcq_sessions",
                partition_key=PartitionKey(path="/session_id"),
                offer_throughput=400
            )
        except:
            pass
        
        self.mcq_sessions_container.create_item(body=session_dict)
        return session_id

    def get_mcq_session(self, session_id: str):
        """Retrieve MCQ session by ID"""
        try:
            from models import MCQSession
            if not hasattr(self, 'mcq_sessions_container'):
                self.mcq_sessions_container = self.database.get_container_client("mcq_sessions")
            
            item = self.mcq_sessions_container.read_item(
                item=session_id,
                partition_key=session_id
            )
            return MCQSession(**item)
        except exceptions.CosmosResourceNotFoundError:
            return None

    def update_mcq_session(
        self,
        session_id: str,
        answers: List,
        current_question_number: int,
        is_complete: bool = False
    ):
        """Update MCQ session with new answer"""
        try:
            session = self.get_mcq_session(session_id)
            if not session:
                raise ValueError(f"MCQ Session {session_id} not found")
            
            session.answers = answers
            session.current_question_number = current_question_number
            session.is_complete = is_complete
            session.updated_at = datetime.utcnow()
            
            # Convert to dict and serialize datetime objects
            session_dict = session.model_dump()
            session_dict = serialize_datetime(session_dict)
            
            self.mcq_sessions_container.upsert_item(body=session_dict)
        except Exception as e:
            print(f"MCQ session update error: {e}")
            raise

    def save_mcq_report(self, report):
        """Save MCQ evaluation report"""
        try:
            if not hasattr(self, 'mcq_reports_container'):
                self.mcq_reports_container = self.database.create_container_if_not_exists(
                    id="mcq_reports",
                    partition_key=PartitionKey(path="/session_id"),
                    offer_throughput=400
                )
            
            # Convert to dict and serialize datetime objects
            report_dict = report.model_dump()
            report_dict = serialize_datetime(report_dict)
            report_dict['id'] = report.session_id
            
            self.mcq_reports_container.upsert_item(body=report_dict)
        except Exception as e:
            print(f"MCQ report save error: {e}")
            raise

    def get_mcq_report(self, session_id: str):
        """Retrieve MCQ report by session ID"""
        try:
            from models import MCQEvaluationReport
            if not hasattr(self, 'mcq_reports_container'):
                self.mcq_reports_container = self.database.get_container_client("mcq_reports")
            
            item = self.mcq_reports_container.read_item(
                item=session_id,
                partition_key=session_id
            )
            return MCQEvaluationReport(**item)
        except exceptions.CosmosResourceNotFoundError:
            return None

database_service = DatabaseService()