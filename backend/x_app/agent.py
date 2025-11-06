"""
ENHANCED REACT AGENT SYSTEM - agent.py
Transforms rule-based workflow into dynamic ReAct agent with tool selection

Key Features:
1. ReAct reasoning loop (Thought -> Action -> Observation)
2. Dynamic tool selection based on user query
3. Multi-turn reasoning with memory
4. Fallback to conversation when no tools needed
"""
import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv

# LangChain imports
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
    from langchain_community.tools import DuckDuckGoSearchRun
    from langchain.tools import tool, Tool
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain.memory import ConversationBufferMemory
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ LangChain packages not available: {e}")
    LANGCHAIN_AVAILABLE = False

# Import Gemini SDK for fallback
try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Configure environment
load_dotenv()
if genai:
    try:
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    except Exception:
        pass


# ------------------------------------------------------------------------------
# Optional: Tiny LLM factory to keep model pick logic in one place
# ------------------------------------------------------------------------------
class LLMFactory:
    @staticmethod
    def create_llm(temperature: float = 0.7):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain packages required for ReAct agent")

        candidates = [
             "gemini-2.0-flash",
            "gemini-2.0-pro",
            "gemini-2.0-flash-latest",
            "gemini-2.0-pro-latest",
        ]
        last_err = None
        for m in candidates:
            try:
                llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                google_api_version="v1",   # ✅ ensures proper API endpoint
                temperature=temperature,
)
                llm = ChatGoogleGenerativeAI(
                    model=m,
                    google_api_key=os.getenv("GOOGLE_API_KEY"),
                    google_api_version="v1",
                    temperature=temperature,
                )

                # Return immediately without testing - assume API key is set
                print(f"✅ Using model: {m}")
                return llm
            except Exception as e:
                last_err = e
                print(f"⚠️ Model {m} failed: {str(e)[:100]}")
        raise RuntimeError(f"All configured models failed: {last_err}")


class BaseAgent:
    """Base class for all agents with common functionality"""
    
    def __init__(self, temperature=0.7):
        self.llm = LLMFactory.create_llm(temperature)
    
    def safe_invoke(self, prompt):
        try:
            response = self.llm.invoke(prompt)
            return response
        except Exception as e:
            print(f"❌ LLM invocation failed: {str(e)}")
            from collections import namedtuple
            MockResponse = namedtuple('MockResponse', ['content'])
            return MockResponse(content=f"Error generating content: {str(e)}")


class OrchestratorAgent(BaseAgent):
    """Central coordinator managing workflow and routing"""
    
    def __init__(self):
        super().__init__(temperature=0.7)
    
    def analyze_query(self, query: str, context: dict) -> dict:
        """Analyze user query and determine next steps"""
        if not LANGCHAIN_AVAILABLE or ChatPromptTemplate is None:
            return {
                "intent": "clarification",
                "next_question": "Could you provide more details about your project?",
                "ready_for_generation": False,
                "reasoning": "System running in limited mode"
            }
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
        
        response = self.safe_invoke(
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
                "next_question": "Could you provide more details about your project goals and requirements?",
                "ready_for_generation": False,
                "reasoning": "Fallback response"
            }


class InformationGatherer(BaseAgent):
    """Extracts and structures information from documents"""
    
    def __init__(self):
        super().__init__(temperature=0.3)
    
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
        
        response = self.safe_invoke(prompt.format(text=text[:4000]))
        
        if '```json' in response.content:
            json_str = response.content.split('```json')[1].split('```')[0]
        else:
            json_str = response.content
        try:
            return json.loads(json_str.strip())
        except Exception:
            return {}
    
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
        
        response = self.safe_invoke(prompt.format(conversation=conversation))
        
        if '```json' in response.content:
            json_str = response.content.split('```json')[1].split('```')[0]
        else:
            json_str = response.content
        try:
            return json.loads(json_str.strip())
        except Exception:
            return {}


class CompetitorAgent(BaseAgent):
    """Performs external research and competitive analysis"""
    
    def __init__(self):
        super().__init__(temperature=0.5)
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
            
            response = self.safe_invoke(
                prompt.format(topic=topic, search_results=search_results[:2000])
            )
            
            if '```json' in response.content:
                json_str = response.content.split('```json')[1].split('```')[0]
            else:
                json_str = response.content
            return json.loads(json_str.strip())
        except Exception as e:
            return {
                "industry_trends": ["Manual research recommended"],
                "best_practices": ["Follow standard development practices"],
                "competitor_insights": [],
                "recommendations": ["Proceed with standard implementation"]
            }


class AnalysisAgent(BaseAgent):
    """Processes and analyzes gathered information"""
    
    def __init__(self):
        super().__init__(temperature=0.4)
    
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
        
        response = self.safe_invoke(prompt.format(
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
                "key_challenges": ["Requirement clarification"],
                "success_factors": ["Clear communication", "Proper planning"],
                "risk_areas": ["Scope creep", "Timeline delays"],
                "opportunities": ["Standard implementation approach"]
            }


# LangChain imports
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_community.tools import DuckDuckGoSearchRun
    from langchain.tools import tool, Tool
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain.memory import ConversationBufferMemory
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    print(f"LangChain import failed: {e}")
    LANGCHAIN_AVAILABLE = False


class SolutionArchitect(BaseAgent):
    """Designs technical architecture and solutions"""
    
    def __init__(self):
        super().__init__(temperature=0.6)
    
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
        
        response = self.safe_invoke(prompt.format(
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
                "database_design": ["PostgreSQL for data storage"],
                "integration_points": ["REST API", "Authentication system"],
                "deployment_strategy": "Cloud-based deployment with Docker"
            }


class DocumentGenerator(BaseAgent):
    """Generates comprehensive concept notes"""
    
    def __init__(self):
        super().__init__(temperature=0.7)
    
    def generate_concept_note(self, project_data: dict) -> str:
        """Generate complete concept note from all gathered data"""
        print(f"💾 Starting concept note generation for: {project_data.get('title', 'Untitled Project')}")
        
        try:
            # Check if user edited the preview - if so, use it as the base
            edited_preview = project_data.get('edited_preview')
            if edited_preview:
                print(f"✅ Using edited preview as base for concept note")
            
            # Safely format the solutions
            formatted_solutions = self._format_solutions(project_data.get('solutions', []))
            print(f"✅ Solutions formatted successfully")
            
            # Prepare other data with safe defaults
            title = project_data.get('title', 'Untitled Project')
            doc_info = str(project_data.get('doc_info', {}))
            conv_summary = str(project_data.get('conv_summary', {}))
            research = str(project_data.get('research', {}))
            analysis = str(project_data.get('analysis', {}))
            architecture = str(project_data.get('architecture', {}))
            
            # Create the prompt template - incorporate edited preview if available
            if edited_preview:
                prompt = ChatPromptTemplate.from_template("""
You are an INTELLIGENT document generator. The user has edited a preview document, and you must:

1. ANALYZE their editing style and patterns
2. UNDERSTAND what they changed and WHY
3. APPLY that same intelligence to the entire concept note

USER'S EDITED PREVIEW:
{edited_preview}

Additional Context:
Project Title: {title}
Selected Internal Solutions: {solutions}
External Research: {research}
Technical Analysis: {analysis}
Architecture Design: {architecture}

INTELLIGENT ANALYSIS INSTRUCTIONS:

1. **Pattern Recognition**:
   - If the user made certain points more specific/detailed, make ALL points that specific
   - If they changed the tone (e.g., from generic to measurable outcomes), apply that tone everywhere
   - If they added metrics or numbers, add similar metrics to other sections
   - If they removed vague language, remove ALL vague language from the entire document

2. **Style Matching**:
   - Match the user's writing style, sentence structure, and vocabulary level
   - If they use action verbs ("reduce", "increase", "streamline"), use similar verbs throughout
   - If they focus on business value, emphasize business value in all sections
   - If they mention specific stakeholders, reference those stakeholders consistently

3. **Content Intelligence**:
   - If they removed generic content, DON'T add generic content elsewhere
   - If they added industry-specific terminology, use that terminology throughout
   - If they emphasized certain benefits (e.g., efficiency, cost savings), prioritize those themes
   - If they structured points in a certain way (e.g., benefit + metric + stakeholder), follow that structure

4. **Section Expansion**:
   Based on the edited preview, generate these additional sections with THE SAME QUALITY and STYLE:
   - Executive Summary (match their tone and specificity)
   - Technical Architecture (detailed, match their technical depth)
   - Internal Solutions Integrated (with descriptions in their style)
   - External Research Findings (relevant to their focus areas)
   - Implementation Roadmap (phases with weeks, match their detail level)
   - Risk Mitigation (address risks relevant to their priorities)
   - Success Metrics (measurable, matching their metric style)

5. **Quality Standards**:
   - Every section should feel like the USER wrote it, not a generic AI
   - Be as specific and detailed as they were
   - Use their vocabulary and phrasing patterns
   - Maintain consistency in tone, style, and depth across ALL sections

IMPORTANT: Don't just copy their edits - LEARN from them and apply that intelligence to create a cohesive, professional document that feels like it was written by the same person throughout.

Generate the complete concept note now:
""")
            else:
                prompt = ChatPromptTemplate.from_template("""
Generate a comprehensive PROJECT CONCEPT NOTE with these sections:

Project Title: {title}
Document Analysis: {doc_info}
Conversation Context: {conv_summary}
Selected Internal Solutions: {solutions}
External Research: {research}
Technical Analysis: {analysis}
Architecture Design: {architecture}

IMPORTANT: Be SPECIFIC and ACTIONABLE. Avoid generic statements.
- Use measurable outcomes where possible
- Reference specific stakeholders and their needs
- Include concrete timelines and metrics
- Focus on business value and ROI

Structure the concept note with:
1. Executive Summary (specific, not generic)
2. Project Objectives (measurable goals)
3. Technical Architecture (detailed with tech stack)
4. Internal Solutions Integrated (with clear benefits)
5. External Research Findings (relevant insights)
6. Implementation Roadmap (phases with specific weeks)
7. Expected Outcomes (measurable benefits with metrics)
8. Risk Mitigation (specific risks and solutions)
9. Success Metrics (quantifiable KPIs)

Make it professional, detailed, and actionable. Write as if you deeply understand this specific project.
""")
            
            print(f"🔍 Invoking LLM for concept note generation")
            if edited_preview:
                response = self.safe_invoke(prompt.format(
                    edited_preview=edited_preview,
                    title=title,
                    solutions=formatted_solutions,
                    research=research,
                    analysis=analysis,
                    architecture=architecture
                ))
            else:
                response = self.safe_invoke(prompt.format(
                    title=title,
                    doc_info=doc_info,
                    conv_summary=conv_summary,
                    solutions=formatted_solutions,
                    research=research,
                    analysis=analysis,
                    architecture=architecture
                ))
            print(f"✅ LLM response received successfully")
            
            # Format the final concept note
            concept_note = f"""# PROJECT CONCEPT NOTE
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

{response.content}

---
**Document Status**: Preview
**Version**: 1.0
**Generated by**: Concept-X AI System
"""
            
            print(f"✅ Concept note generated successfully: {len(concept_note)} characters")
            return concept_note
            
        except Exception as e:
            print(f"❌ Error in concept note generation: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Create a fallback concept note
            fallback_note = f"""# PROJECT CONCEPT NOTE
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Executive Summary

This concept note outlines the approach for {project_data.get('title', 'the project')}. Due to technical limitations, this is a simplified version.

## Project Objectives

- Successfully implement the required functionality
- Meet stakeholder expectations
- Deliver on time and within scope

## Technical Approach

A detailed technical approach will be developed based on the requirements.

## Implementation Plan

The project will be implemented in phases with regular checkpoints.

---
**Document Status**: Preview (Error Recovery)
**Version**: 1.0
**Generated by**: Concept-X AI System
"""
            
            print(f"✅ Fallback concept note generated: {len(fallback_note)} characters")
            return fallback_note
    
    def _format_solutions(self, solutions: list) -> str:
        """Format internal solutions for prompt"""
        if not solutions:
            return "No internal solutions selected"
        
        formatted = []
        for sol in solutions:
            try:
                # Handle both model instances and dictionaries
                if hasattr(sol, 'name') and hasattr(sol, 'description'):
                    formatted.append(f"- {sol.name}: {sol.description}")
                elif isinstance(sol, dict) and 'name' in sol and 'description' in sol:
                    formatted.append(f"- {sol['name']}: {sol['description']}")
                else:
                    # Fallback for any other format
                    formatted.append(f"- {str(sol)}")
            except Exception as e:
                print(f"⚠️ Error formatting solution: {e}")
                formatted.append(f"- Solution (format error): {str(sol)[:50]}...")
                
        return "\n".join(formatted)


# ============================== ReAct Agent System (Fixed) ==============================

from langchain.memory import ConversationBufferMemory

class ReActAgent:
    """ReAct Agent System (LangChain 0.3.x compatible)"""

    def __init__(self):
        # Use the same LLM factory you defined above (already probes models)
        self.llm = LLMFactory.create_llm(temperature=0.2)

        # Tools (search as an example; add more if you like)
        self.tools = [
            DuckDuckGoSearchRun()
        ]

        # ReAct-style prompt template (standard format)
        self.prompt = PromptTemplate.from_template("""
Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}""")

        # Build the ReAct agent graph
        self.agent_graph = create_react_agent(self.llm, self.tools, self.prompt)

        # Memory (return_messages=True to feed back into the prompt)
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        # Final executor
        self.executor = AgentExecutor(
            agent=self.agent_graph,
            tools=self.tools,
            memory=self.memory,
            verbose=False,
            handle_parsing_errors=True,
            max_iterations=6,
        )

    def react(self, input_message: str) -> str:
        """Run one ReAct step"""
        # AgentExecutor expects a dict with "input"
        result = self.executor.invoke({"input": input_message})
        # Standard key is "output"; fall back to str if not present
        return result.get("output") or str(result)


class ReActExecutor:
    """Wrapper around ReActAgent providing helper entry points."""

    def __init__(self):
        self.agent = ReActAgent()
        # ✨ an LLM for quick small-talk/regular chat replies
        self.smalltalk_llm = LLMFactory.create_llm(temperature=0.6)

    # ✨ helper to detect greetings / short chit-chat
    @staticmethod
    def _is_smalltalk(text: str) -> bool:
        if not text:
            return False
        t = text.strip().lower()
        greetings = {
            "hi", "hello", "hey", "yo", "hola", "sup",
            "good morning", "good afternoon", "good evening"
        }
        if t in greetings or any(t.startswith(g) for g in greetings):
            return True
        # short statements without a question mark are probably chit-chat
        return (len(t.split()) <= 4) and ("?" not in t)

    def execute(self, input_message: str, context: dict | None = None, project: Any | None = None) -> str:
        # small talk path
        if self._is_smalltalk(input_message):
            prompt = ("You are a warm, concise assistant. Reply briefly:\n\n" + input_message)
            resp = self.smalltalk_llm.invoke(prompt)
            return getattr(resp, "content", str(resp))

        # ---- INJECT DOCUMENT CONTEXT HERE ----
        doc = (context or {}).get('document_text') or ''
        if doc:
            # keep prompt safe and bounded
            doc_snippet = doc[:4000]
            wrapped = (
                "You have access to the following document context (truncated):\n"
                "----- DOCUMENT CONTEXT START -----\n"
                f"{doc_snippet}\n"
                "----- DOCUMENT CONTEXT END -----\n\n"
                f"User request: {input_message}\n"
                "If the user asks to analyze the PDF/document, use the context above. "
                "Do not say you lack access to the PDF."
            )
            return self.agent.react(wrapped)

        # no context → normal ReAct
        return self.agent.react(input_message)

    def process_user_input(self, input_message: str, project: Any | None = None, context: dict | None = None) -> dict:
        reply = self.execute(input_message, context=context, project=project)
        return {"response": reply, "actions": []}

# ---------------- Compatibility shim for old imports ----------------
class HybridOrchestrator(ReActExecutor):
    """Backwards-compatible wrapper so existing imports continue to work."""

    def __init__(self):  # pragma: no cover - simple delegation
        super().__init__()
# -------------------------------------------------------------------


# Singleton instance and convenience function
react_executor = ReActExecutor()

def react_agent(input_message: str) -> str:
    return react_executor.execute(input_message)
# ============================ /ReAct Agent System (Fixed) ===============================



# ReAct Agent Functions
def react_agent(input_message: str) -> str:
    """ReAct agent function"""
    return react_executor.execute(input_message)


def generate_preview(raw_input: str, highlight_points: str = None) -> str:
    model = genai.GenerativeModel('gemini-2.0-flash')

    """
    Convert raw client input into a DETAILED, BEAUTIFULLY FORMATTED preview
    """
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        raise RuntimeError(f"Gemini configuration failed: {e}")
    
    prompt = f"""You are a senior business analyst. Transform client requirements into a comprehensive, professional document.


CLIENT'S RAW INPUT:
{raw_input}


KEY POINTS TO EMPHASIZE:
{highlight_points if highlight_points else "None specified"}


CRITICAL INSTRUCTION: Analyze the CLIENT'S ACTUAL INPUT and create a preview SPECIFIC to their project. DO NOT use generic school/hospital/e-commerce examples unless that's what the client described.


TASK: Create a detailed preview that looks like a professional business document.


FORMAT STRUCTURE:


PROJECT TITLE & OVERVIEW
────────────────────────────────────────


[Extract or create a clear project title from the client's input]


[Write 2-3 comprehensive paragraphs explaining THIS SPECIFIC project based on what the client described. Each paragraph should be 4-6 sentences. Make it flow naturally. Use confident language but stay true to the client's vision.]



PRIMARY OBJECTIVES
────────────────────────────────────────


[Identify 5-8 specific objectives from the client's input. Write each as a clear statement.]


- [Objective 1 based on client's actual needs]
- [Objective 2 with measurable outcomes if mentioned]
- [Objective 3 focusing on user benefits from their description]
- [Continue with 5-8 objectives total - all must relate to THIS project]



TARGET USERS & STAKEHOLDERS
────────────────────────────────────────


[Identify who will use this system based on the client's input. If they mentioned teachers/students, use those. If they mentioned customers/admins, use those. If they mentioned doctors/patients, use those.]


[Stakeholder Group 1 from client input]: [2-3 sentences describing their needs, challenges, and how this helps them based on the project description]


[Stakeholder Group 2 from client input]: [2-3 sentences describing their needs and benefits specific to this project]


[Stakeholder Group 3 from client input]: [2-3 sentences describing their role and benefits]


[Continue for all stakeholder groups mentioned or implied in the client's input]



CORE FUNCTIONAL REQUIREMENTS
────────────────────────────────────────


[Identify 5-7 major functional areas from the CLIENT'S description. Each should have a descriptive title and explanation.]


[Requirement 1 Title - extracted from client needs]
[Write 2-3 sentences explaining what this requirement does, why it matters, and how it serves the users. Base this entirely on the client's input, not generic examples.]


[Requirement 2 Title - extracted from client needs]
[Write 2-3 sentences specific to this project's needs.]


[Requirement 3 Title - extracted from client needs]
[Write 2-3 sentences specific to this project's needs.]


[Continue with all major requirements identified from the input]



SPECIAL REQUIREMENTS & UNIQUE FEATURES
────────────────────────────────────────


[Look for unique aspects in the client's input - AI, automation, specific integrations, special workflows, etc.]


[Feature Category 1 if mentioned]: [2-3 sentences about this specific capability for this project]


[Feature Category 2 if mentioned]: [2-3 sentences about how this works in their context]


[Feature Category 3 if mentioned]: [2-3 sentences about implementation approach]



TECHNICAL CONSIDERATIONS
────────────────────────────────────────


[Identify 5-8 technical requirements based on the project scope and industry. Consider: scale, security, integrations, platforms, compliance]


- [Technical requirement 1 relevant to this project]
- [Technical requirement 2 based on industry/domain]
- [Technical requirement 3 addressing scalability/security]
- [Continue with technical needs specific to this solution]



EXPECTED OUTCOMES & BENEFITS
────────────────────────────────────────


[Identify 5-7 specific, measurable benefits this project will deliver based on the objectives and requirements]


- [Benefit 1 with measurable outcome if possible]
- [Benefit 2 specific to the stakeholders mentioned]
- [Benefit 3 addressing business value]
- [Continue with 5-7 benefits total]



CRITICAL FORMATTING RULES:
✓ Use section headers in CAPS followed by line separator (────)
✓ Write in paragraphs for descriptions (NOT bullet points unless listing)
✓ Each requirement gets 2-3 flowing sentences
✓ Professional business document tone
✓ Clear spacing between sections (double line break)
✓ 500-800 words total
✓ NO asterisks, NO markdown - just clean text with line separators


MOST IMPORTANT: Every section must be filled with content SPECIFIC to this client's input. Do NOT copy the example content about schools, students, or teachers unless the client specifically mentioned education. Analyze what THEY want and describe THEIR project.


OUTPUT: Professional document following the structure above with content specific to: {raw_input[:100]}"""

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        # Extract text from response
        preview_text = getattr(response, 'text', '') or ''
        if not preview_text.strip():
            # Fallback to candidates/parts if text is empty
            cand = getattr(response, 'candidates', []) or []
            if cand:
                content = getattr(cand[0], 'content', None)
                parts = getattr(content, 'parts', None) if content else None
                if parts:
                    for p in parts:
                        pt = getattr(p, 'text', None)
                        if pt and pt.strip():
                            preview_text = pt
                            break
        
        if not preview_text.strip():
            raise RuntimeError("Empty response from Gemini")
        
        return preview_text.strip()
    
    except Exception as e:
        raise RuntimeError(f"Preview generation failed: {e}")


# ===== Dynamic Clarification Questions (content-driven) =====
def _clean_json_response(text: str) -> str:
    text = (text or "").strip()
    if text.startswith('```'):
        parts = text.split('```')
        for part in parts:
            p = part.strip()
            if p.startswith('json'):
                p = p[4:].strip()
            if p.startswith('[') or p.startswith('{'):
                text = p
                break
    # truncate after closing bracket of top-level array
    if text.startswith('['):
        bracket = 0
        for i, ch in enumerate(text):
            if ch == '[':
                bracket += 1
            elif ch == ']':
                bracket -= 1
                if bracket == 0:
                    text = text[:i+1]
                    break
    return text


 


def _validate_and_enhance_questions(questions: list, uploaded_files_count: int) -> list:
    if not isinstance(questions, list):
        return []
    out = []
    for i, q in enumerate(questions):
        if isinstance(q, dict) and q.get('question'):
            out.append({
                'id': q.get('id', i+1),
                'question': q['question'],
                'context_reference': q.get('context_reference', ''),
                'detected_value': q.get('detected_value'),
                'question_type': q.get('question_type', 'clarification'),
                'field_type': q.get('field_type', 'text_input'),
                'importance': q.get('importance', 'medium'),
                'skip_allowed': q.get('skip_allowed', True),
                'why_asking': q.get('why_asking', 'Clarifies ambiguous information')
            })
    # ensure a doc prompt if none uploaded
    if uploaded_files_count == 0:
        has_doc_q = any('document' in q['question'].lower() or 'file' in q['question'].lower() for q in out)
        if not has_doc_q and len(out) < 5:
            out.append({
                'id': len(out) + 1,
                'question': 'Do you have any supporting documents (RFP, specs, wireframes) to share?',
                'context_reference': 'No documents uploaded',
                'detected_value': None,
                'question_type': 'missing_info',
                'field_type': 'file_upload',
                'importance': 'high',
                'skip_allowed': True,
                'why_asking': 'Documents provide critical context and requirements'
            })
    return out[:5]


def generate_dynamic_clarification_questions(raw_input: str = None, pdf_text: str = None, audio_transcript: str = None, uploaded_files_count: int = 0) -> list:
    """Generate content-based clarification questions using Gemini SDK."""
    model = genai.GenerativeModel(
    'gemini-2.0-flash',
    generation_config={"response_mime_type": "application/json"}
)
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        raise RuntimeError(f"Gemini configuration failed: {e}")

    # Combine all available context
    parts = []
    if raw_input:
        parts.append(f"USER DESCRIPTION:\n{raw_input}")
    if pdf_text:
        parts.append(f"\nPDF DOCUMENT:\n{pdf_text[:5000]}")  # First 5000 chars
    if audio_transcript:
        parts.append(f"\nAUDIO TRANSCRIPT:\n{audio_transcript}")
    
    combined = "\n\n".join(parts)
    
    if not combined.strip():
        # Still query LLM with a generic baseline context
        combined = (
            "NO SPECIFIC CONTEXT PROVIDED. The user started a session but did not supply analyzable text. "
            "Generate universally useful, highly-informative clarification questions for early project scoping."
        )

    prompt = f"""Analyze this project documentation and generate 3-5 intelligent clarification questions.

PROJECT CONTEXT:
{combined}

FILES UPLOADED: {uploaded_files_count}

INSTRUCTIONS:
1. Read the content carefully
2. Identify gaps, ambiguities, or missing critical information
3. Generate questions that are SPECIFIC to THIS project
4. Don't ask generic questions - be contextual

Example: If document mentions "healthcare app" but not users, ask "Who are the primary users - doctors, patients, or administrators?"

Return JSON array:
[
  {{
    "id": 1,
    "question": "Your specific question here",
    "context_reference": "What section of their input triggered this",
    "detected_value": null,
    "question_type": "missing_info",
    "field_type": "text_input",
    "importance": "critical",
    "skip_allowed": false,
    "why_asking": "Brief reason"
  }}
]
"""

    try:
        # Use the working model and request JSON directly
        model = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"response_mime_type": "application/json"}
        )
        resp = model.generate_content(prompt)

        # Robustly extract text from the response
        def _extract_resp_text(r):
            t = getattr(r, 'text', '') or ''
            if t and t.strip():
                return t
            # Fallback to candidates/parts if text is empty
            cand = getattr(r, 'candidates', []) or []
            if cand:
                content = getattr(cand[0], 'content', None)
                parts = getattr(content, 'parts', None) if content else None
                if parts:
                    for p in parts:
                        pt = getattr(p, 'text', None)
                        if pt and pt.strip():
                            return pt
            return ''

        raw_text = _extract_resp_text(resp)
        if not raw_text.strip():
            raise RuntimeError("Empty response from Gemini")

        text = _clean_json_response(raw_text)
        data = json.loads(text)

        validated = _validate_and_enhance_questions(data, uploaded_files_count)
        print(f"✅ Generated {len(validated)} dynamic questions")
        return validated

    except json.JSONDecodeError:
        raise
    except Exception:
        raise


# === Bulk upload PDF solutions ===
PRODUCT_DETAILS = {
    'ai_compliance_checking': {
        'name': 'eSAFE',
        'description': 'eSAFE is a comprehensive e-governance platform that assists businesses in identifying their correct National Industrial Classification (NIC) code through an AI-powered chatbot. It automates compliance questionnaire completion and manages the subsequent reporting and verification workflows across a hierarchical office structure.',
        'tagline': 'AI-Powered Compliance & NIC Code Identification'
    },
    'asset': {
        'name': 'Asset Trace',
        'description': 'Asset Trace is an advanced asset management solution that provides real-time visibility and control over organizational assets. Using dynamic QR codes and a centralized dashboard, it streamlines tracking, maintenance scheduling, and utilization analytics to reduce costs and improve operational efficiency.',
        'tagline': 'Effortless and Effective Asset Management'
    },
    'blockchain': {
        'name': 'Hyperledger',
        'description': 'This platform leverages blockchain technology to provide secure, transparent, and immutable digital certificate issuance. Enhanced with AI assistance, it automates the creation, management, and distribution of various digital credentials, ensuring they are tamper-proof and easily verifiable.',
        'tagline': 'Blockchain-Powered Digital Certification'
    },
    'convo': {
        'name': 'Convo AI',
        'description': 'Convo AI is an industry-leading voice agent that transforms call-based communications using advanced AI. It enables natural, human-like conversations to automate customer service, sales outreach, and internal queries, providing 24/7 support and multi-language capabilities.',
        'tagline': 'Transforming Communication with Voice Intelligence'
    },
    'fastaides': {
        'name': 'FastAides',
        'description': 'FastAides is a comprehensive healthcare and service platform connecting customers with vendors like pharmacies and service providers. It facilitates vendor onboarding, appointment booking, prescription-based orders, and AI-chatbot assistance for a seamless user experience.',
        'tagline': 'Your Comprehensive Health & Service Partner'
    },
    'helpybo': {
        'name': 'Helpybo Multi Agents Builder',
        'description': 'Helpybo is an enterprise-grade platform for building, deploying, and managing collaborative AI agents. It enables multiple specialized agents to work in harmony, solving complex challenges, optimizing workflows, and driving intelligent automation across business processes.',
        'tagline': 'Collaborative Multi-Agent Intelligence'
    },
    'image_identifier': {
        'name': 'Image Identifier',
        'description': 'This photography platform uses advanced facial recognition technology to connect users with photographers. Users can upload a personal photo to find their pictures from event galleries, while photographers can manage their events and photo collections efficiently.',
        'tagline': 'AI-Powered Event Photo Discovery'
    },
    'mcq': {
        'name': 'AI-Powered MCQ Generator',
        'description': 'This tool automates the creation of multiple-choice questions from text-based PDFs like textbooks and manuals. Leveraging advanced NLP and LLMs, it generates topic-specific, customizable assessments for educational and corporate training environments.',
        'tagline': 'Streamlining Learner Evaluation'
    },
    'neobench': {
        'name': 'NeoBench',
        'description': 'NeoBench is an AI-powered Learning Management Solution designed for modern workforce upskilling. It offers a centralized content pool, collaborative tools, real-time analytics, and personalized AI recommendations to create a dynamic and scalable learning experience.',
        'tagline': 'Powering Modern Workforce Upskilling'
    },
    'neoleadx': {
        'name': 'Neo LeadX',
        'description': 'Neo LeadX is an AI-driven lead management platform that optimizes the entire lead handling process. It provides real-time alerts, AI-powered prioritization, and multi-channel outreach automation to help sales teams respond faster and improve conversion rates.',
        'tagline': 'Intelligent Lead Management & Engagement'
    },
    'omnia': {
        'name': 'Omnia',
        'description': 'Omnia is an AI-driven healthcare platform that enhances clinical efficiency through voice-to-clinical note transcription and a robust teleconsultation system. It reduces administrative burdens, improves documentation accuracy, and ensures compliance with healthcare standards like HIPAA.',
        'tagline': 'AI-Driven Healthcare Platform'
    },
    'projectx': {
        'name': 'Project X',
        'description': 'Project X is an end-to-end project management platform that automates the entire project lifecycle from concept note to prototype. It uses AI agents to accelerate requirement extraction, estimation, design, and task assignment, dramatically reducing project timelines.',
        'tagline': 'End-to-End Project Lifecycle Automation'
    },
    'replygenie': {
        'name': 'Replygenie',
        'description': 'Replygenie is an AI-powered social media management tool that automates and personalizes responses to comments across platforms like Facebook and Instagram. It uses sentiment analysis to craft context-aware replies, strengthening customer relationships and brand image.',
        'tagline': 'AI-Powered Social Media Engagement'
    },
    'rezi': {
        'name': 'Rezi',
        'description': 'Rezi is a next-generation AI resume analyzer that transforms talent acquisition. It automates resume screening and matches candidates to job descriptions with high accuracy, enabling faster, data-driven hiring decisions and a streamlined recruitment process.',
        'tagline': 'AI-Powered Resume Analysis & Matching'
    },
}


def bulk_upload_products(pdf_directory: str) -> dict:
    from .utils import vector_store
    from .models import InternalSolution

    print("Starting PDF upload process...")
    print(f"Looking for PDFs in: {pdf_directory}\n")

    if not os.path.exists(pdf_directory):
        print(f"ERROR: Directory not found: {pdf_directory}")
        return {"uploaded": 0, "failed": 0}

    uploaded_count = 0
    failed_count = 0

    # Walk recursively to find PDFs anywhere under pdf_directory
    for root, _, files in os.walk(pdf_directory):
        for filename in files:
            if filename.lower().endswith('.pdf'):
                # derive key from filename
                file_key = (
                    filename.lower().replace('.pdf', '').replace('_2', '').replace('_1', '')
                )
                # derive key from parent folder name as fallback
                folder_key = os.path.basename(root).lower()

                # normalize known variants
                def normalize_key(k: str) -> str:
                    if 'helpybo' in k:
                        return 'helpybo'
                    if 'neoleadx' in k:
                        return 'neoleadx'
                    if 'projectx' in k:
                        return 'projectx'
                    return k

                file_key = normalize_key(file_key)
                folder_key = normalize_key(folder_key)

                key = None
                if file_key in PRODUCT_DETAILS:
                    key = file_key
                elif folder_key in PRODUCT_DETAILS:
                    key = folder_key

                full_filepath = os.path.join(root, filename)

                if key:
                    product_info = PRODUCT_DETAILS[key]
                    solution_name = product_info['name']
                    description = product_info['description']

                    print(f" Uploading: {full_filepath}")
                    print(f"   → Key: {key} | Name: {solution_name}")

                    try:
                        data = vector_store.create_embedding_from_pdf(full_filepath, solution_name, description)
                        solution = InternalSolution.objects.create(**data)
                        print(f"   Success: {solution.name}\n")
                        uploaded_count += 1
                    except Exception as e:
                        print(f"   Error: {e}\n")
                        failed_count += 1
                else:
                    print(f"  Warning: No mapping found for '{full_filepath}' (file_key: '{file_key}', folder_key: '{folder_key}'). Skipping.\n")

    if uploaded_count > 0:
        try:
            vector_store.build_index()
        except Exception as e:
            print(f" Index rebuild error: {e}")

    print("\n" + "="*50)
    print("UPLOAD SUMMARY")
    print("="*50)
    print(f" Uploaded: {uploaded_count}")
    print(f" Failed: {failed_count}")

    try:
        from .models import InternalSolution as IS
        total = IS.objects.count()
        print(f" Total solutions in database: {total}")
        print("\nSolutions in database:")
        for sol in IS.objects.all():
            print(f"  • {sol.name}")
    except Exception as e:
        print(f" Could not verify: {e}")

    print("\n Script completed!")
    return {"uploaded": uploaded_count, "failed": failed_count}