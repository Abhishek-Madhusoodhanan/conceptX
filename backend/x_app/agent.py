# agent .py
"""
All LangChain Agents in ONE file for simplicity
"""
import os
import json
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.tools import DuckDuckGoSearchRun


class OrchestratorAgent:
    """Central coordinator managing workflow and routing"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.7
        )
    
    def analyze_query(self, query: str, context: dict) -> dict:
        """Analyze user query and determine next steps"""
        prompt = ChatPromptTemplate.from_template("""
You are an orchestrator agent managing a multi-agent workflow system.

User Query: {query}
Conversation History: {history}
Document Context: {doc_context}

Analyze this query and determine:
1. Is this a clarification response or new request?
2. Do we have enough information to proceed?
3. What should be the next question (if needed)?

Respond in JSON format:
{{
    "intent": "clarification|ready|processing",
    "next_question": "question to ask user or null",
    "ready_for_generation": true/false,
    "reasoning": "brief explanation"
}}
""")
        
        history = context.get('history', [])
        doc_context = context.get('document_summary', 'No document uploaded')
        
        response = self.llm.invoke(
            prompt.format(
                query=query,
                history=json.dumps(history[-5:]),
                doc_context=doc_context
            )
        )
        
        return self._parse_response(response.content)
    
    def _parse_response(self, response: str) -> dict:
        """Parse LLM JSON response"""
        try:
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                response = response.split('```')[1].split('```')[0]
            
            return json.loads(response.strip())
        except:
            return {
                "intent": "clarification",
                "next_question": response,
                "ready_for_generation": False,
                "reasoning": "Parsed as text response"
            }


class InformationGatherer:
    """Extracts and structures information from documents"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.3
        )
    
    def extract_document_info(self, text: str) -> dict:
        """Extract key information from uploaded document"""
        prompt = ChatPromptTemplate.from_template("""
Analyze this document and extract key information:

Document Text:
{text}

Extract and structure:
1. Main Topic/Purpose
2. Key Requirements
3. Stakeholders mentioned
4. Technical aspects
5. Constraints or limitations

Return as JSON:
{{
    "topic": "...",
    "requirements": [...],
    "stakeholders": [...],
    "technical_aspects": [...],
    "constraints": [...]
}}
""")
        
        response = self.llm.invoke(prompt.format(text=text[:4000]))
        
        try:
            if '```json' in response.content:
                json_str = response.content.split('```json')[1].split('```')[0]
            else:
                json_str = response.content
            return json.loads(json_str.strip())
        except:
            return {
                "topic": "Document analysis",
                "requirements": [],
                "stakeholders": [],
                "technical_aspects": [],
                "constraints": []
            }
    
    def summarize_conversation(self, messages: list) -> dict:
        """Summarize conversation context"""
        conversation = "\n".join([
            f"{m['role']}: {m['content']}" 
            for m in messages[-10:]
        ])
        
        prompt = ChatPromptTemplate.from_template("""
Summarize this conversation into structured data:

{conversation}

Extract:
{{
    "project_goal": "...",
    "target_users": "...",
    "timeline": "...",
    "technical_constraints": "...",
    "additional_context": "..."
}}
""")
        
        response = self.llm.invoke(prompt.format(conversation=conversation))
        
        try:
            if '```json' in response.content:
                json_str = response.content.split('```json')[1].split('```')[0]
            else:
                json_str = response.content
            return json.loads(json_str.strip())
        except:
            return {
                "project_goal": "Not specified",
                "target_users": "Not specified",
                "timeline": "Not specified",
                "technical_constraints": "None specified"
            }


class CompetitorAgent:
    """Performs external research and competitive analysis"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.5
        )
        self.search = DuckDuckGoSearchRun()
    
    def research_topic(self, topic: str, context: dict) -> dict:
        """Perform web search and analyze results"""
        try:
            query = f"{topic} implementation best practices architecture"
            search_results = self.search.run(query)
            
            prompt = ChatPromptTemplate.from_template("""
Based on these search results about {topic}:

{search_results}

Provide analysis:
{{
    "industry_trends": [...],
    "best_practices": [...],
    "competitor_insights": [...],
    "recommendations": [...]
}}
""")
            
            response = self.llm.invoke(
                prompt.format(topic=topic, search_results=search_results[:2000])
            )
            
            if '```json' in response.content:
                json_str = response.content.split('```json')[1].split('```')[0]
            else:
                json_str = response.content
            return json.loads(json_str.strip())
        except Exception as e:
            return {
                "industry_trends": ["Error performing search"],
                "best_practices": ["Manual research recommended"],
                "competitor_insights": [],
                "recommendations": []
            }


class AnalysisAgent:
    """Processes and analyzes gathered information"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.4
        )
    
    def analyze_requirements(self, data: dict) -> dict:
        """Analyze project requirements and generate insights"""
        prompt = ChatPromptTemplate.from_template("""
Analyze this project data and provide insights:

Document Info: {doc_info}
Conversation Summary: {conv_summary}
External Research: {research}

Provide structured analysis:
{{
    "key_challenges": [...],
    "success_factors": [...],
    "risk_areas": [...],
    "opportunities": [...]
}}
""")
        
        response = self.llm.invoke(prompt.format(
            doc_info=str(data.get('doc_info', {})),
            conv_summary=str(data.get('conv_summary', {})),
            research=str(data.get('research', {}))
        ))
        
        try:
            if '```json' in response.content:
                json_str = response.content.split('```json')[1].split('```')[0]
            else:
                json_str = response.content
            return json.loads(json_str.strip())
        except:
            return {
                "key_challenges": [],
                "success_factors": [],
                "risk_areas": [],
                "opportunities": []
            }


class SolutionArchitect:
    """Designs technical architecture and solutions"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.6
        )
    
    def design_architecture(self, data: dict, internal_solutions: list) -> dict:
        """Design comprehensive solution architecture"""
        prompt = ChatPromptTemplate.from_template("""
Design a technical architecture based on:

Project Requirements: {requirements}
Analysis Insights: {analysis}
Internal Solutions Available: {solutions}
External Research: {research}

Provide detailed architecture:
{{
    "frontend_stack": [...],
    "backend_stack": [...],
    "database_design": [...],
    "integration_points": [...],
    "deployment_strategy": "..."
}}
""")
        
        response = self.llm.invoke(prompt.format(
            requirements=str(data.get('requirements', {})),
            analysis=str(data.get('analysis', {})),
            solutions=str([s.name for s in internal_solutions]),
            research=str(data.get('research', {}))
        ))
        
        try:
            if '```json' in response.content:
                json_str = response.content.split('```json')[1].split('```')[0]
            else:
                json_str = response.content
            return json.loads(json_str.strip())
        except:
            return {
                "frontend_stack": ["React", "Tailwind CSS"],
                "backend_stack": ["Django", "PostgreSQL"],
                "database_design": [],
                "integration_points": [],
                "deployment_strategy": "Cloud-based deployment"
            }


class DocumentGenerator:
    """Generates comprehensive concept notes"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            google_api_key=os.getenv('GOOGLE_API_KEY'),
            temperature=0.7
        )
    
    def generate_concept_note(self, project_data: dict) -> str:
        """Generate complete concept note from all gathered data"""
        prompt = ChatPromptTemplate.from_template("""
Generate a comprehensive PROJECT CONCEPT NOTE with these sections:

Project Title: {title}
Document Analysis: {doc_info}
Conversation Context: {conv_summary}
Selected Internal Solutions: {solutions}
External Research: {research}
Technical Analysis: {analysis}
Architecture Design: {architecture}

Structure the concept note with:
1. Executive Summary
2. Project Objectives
3. Technical Architecture (detailed)
4. Internal Solutions Integrated (with descriptions)
5. External Research Findings
6. Implementation Roadmap (phases with weeks)
7. Expected Outcomes
8. Risk Mitigation
9. Success Metrics

Make it professional, detailed, and actionable. Use markdown formatting.
""")
        
        response = self.llm.invoke(prompt.format(
            title=project_data.get('title', 'Untitled Project'),
            doc_info=str(project_data.get('doc_info', {})),
            conv_summary=str(project_data.get('conv_summary', {})),
            solutions=self._format_solutions(project_data.get('solutions', [])),
            research=str(project_data.get('research', {})),
            analysis=str(project_data.get('analysis', {})),
            architecture=str(project_data.get('architecture', {}))
        ))
        
        concept_note = f"""# PROJECT CONCEPT NOTE
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

{response.content}

---
**Document Status**: Preview
**Version**: 1.0
**Generated by**: Concept-X AI System
"""
        
        return concept_note
    
    def _format_solutions(self, solutions: list) -> str:
        """Format internal solutions for prompt"""
        if not solutions:
            return "No internal solutions selected"
        
        formatted = []
        for sol in solutions:
            formatted.append(f"- {sol.name}: {sol.description}")
        return "\n".join(formatted)