from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    azure_openai_api_version: str
    
    # Azure Document Intelligence
    azure_document_intelligence_endpoint: str
    azure_document_intelligence_key: str
    
    # Cosmos DB
    cosmos_uri: str
    cosmos_key: str
    cosmos_database: str
    
    # App Settings
    environment: str = "development"
    debug: bool = False
    api_version: str = "v1"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()