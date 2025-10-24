"""
Geography Data Acquisition Agent using GPT-4 0-mini and LangChain
"""

import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from langchain.agents import AgentType, initialize_agent
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder

from .tools import google_search_tool, download_content_tool, check_duplicate_tool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeographyAgent:
    """Agent for acquiring geography study materials"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize the agent with GPT-4 0-mini"""
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4-0125-preview",  # GPT-4 0-mini
            temperature=0,
            openai_api_key=self.api_key
        )
        
        # Set up memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Initialize agent with tools
        self.agent = initialize_agent(
            tools=[
                google_search_tool,
                download_content_tool,
                check_duplicate_tool
            ],
            llm=self.llm,
            agent=AgentType.OPENAI_FUNCTIONS,
            memory=self.memory,
            verbose=True
        )
        
    def search_and_download(self, subject: str, subtopic: str, source_type: str) -> Dict[str, Any]:
        """
        Search for and download study materials for a specific subtopic
        
        Args:
            subject: Main subject (e.g., "Physical Geography")
            subtopic: Specific topic (e.g., "Geomorphology")
            source_type: Type of source (e.g., "NCERT", "Vision IAS")
            
        Returns:
            Dict with status and results
        """
        try:
            # Construct search query
            query = f"{subject} {subtopic} {source_type} UPSC PDF"
            
            # Let the agent handle the workflow
            result = self.agent.run({
                "input": f"Search for and download study materials about {subtopic} in {subject}. "
                        f"Look specifically for {source_type} materials. "
                        f"Use these steps:\n"
                        f"1. Search using the query: {query}\n"
                        f"2. For each result:\n"
                        f"   - Download if it's a PDF\n"
                        f"   - Convert to PDF if it's a webpage\n"
                        f"   - Skip if duplicate\n"
                        f"3. Return a summary of what was downloaded"
            })
            
            return {
                "status": "success",
                "subject": subject,
                "subtopic": subtopic,
                "source_type": source_type,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return {
                "status": "error",
                "subject": subject,
                "subtopic": subtopic,
                "source_type": source_type,
                "error": str(e)
            }
            
    def process_geography_syllabus(self) -> Dict[str, Any]:
        """Process the entire geography syllabus"""
        
        syllabus = {
            "Physical Geography": [
                "Geomorphology",
                "Climate and Weather",
                "Natural Vegetation and Wildlife",
                "Resources and Agriculture"
            ],
            "Human Geography": [
                "Population and Settlement",
                "Urbanization and Migration",
                "Economic Geography",
                "Political Geography"
            ],
            "Environmental Geography": [
                "Biodiversity and Conservation",
                "Pollution and Climate Change",
                "Environmental Policies and Acts"
            ]
        }
        
        source_types = [
            "NCERT",
            "Vision IAS",
            "Insights IAS",
            "Previous Year Questions"
        ]
        
        results = []
        
        try:
            for subject, subtopics in syllabus.items():
                for subtopic in subtopics:
                    for source_type in source_types:
                        result = self.search_and_download(
                            subject=subject,
                            subtopic=subtopic,
                            source_type=source_type
                        )
                        results.append(result)
                        
            return {
                "status": "success",
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Syllabus processing failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "partial_results": results
            }