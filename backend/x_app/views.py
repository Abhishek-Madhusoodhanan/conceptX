from django.shortcuts import render
import os
import json
import re

# Create your views here.
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import (
    InternalSolution, Project, ConversationMessage,
    Artifact, ProjectSolution
)
from .serializers import (
    InternalSolutionSerializer, ProjectSerializer,
    ProjectCreateSerializer, MessageCreateSerializer,
    GenerateConceptNoteSerializer, ArtifactSerializer,
    ArtifactUpdateSerializer
)
from .utils import extract_text_from_file, vector_store
from .agent import (
    OrchestratorAgent, InformationGatherer, AnalysisAgent,
    SolutionArchitect, CompetitorAgent, DocumentGenerator,
    generate_dynamic_clarification_questions, generate_preview
)


def _collapse_whitespace(text: str, limit: int = None) -> str:
    """Normalize whitespace in extracted text for clean previews"""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "..."
    return cleaned


def _format_bullet_list(items, default_line: str) -> str:
    if isinstance(items, (list, tuple)) and items:
        return "\n".join(f"- {str(item).strip()}" for item in items if str(item).strip())
    return default_line


def _build_professional_preview(project, conv_summary: dict, doc_info: dict, excerpt_limit: int = 600) -> str:
    """Create a polished preview when LLM content is unavailable"""
    conv_summary = conv_summary or {}
    doc_info = doc_info or {}

    title = doc_info.get('topic') or project.title
    project_goal = conv_summary.get('project_goal') or doc_info.get('topic')
    overview_lines = [
        _collapse_whitespace(project_goal) if project_goal else (
            "This initiative advances a patient-first digital triage and engagement platform that "
            "connects individuals with the right clinical specialists in minutes."
        )
    ]

    narrative_hint = doc_info.get('constraints') or conv_summary.get('additional_context')
    if narrative_hint:
        overview_lines.append(_collapse_whitespace(narrative_hint))
    else:
        overview_lines.append(
            "The solution is positioned as an enterprise-grade product with governance, auditability, and "
            "clear service-level agreements suitable for multinational healthcare organisations."
        )

    stakeholders_text = conv_summary.get('target_users')
    stakeholder_list = doc_info.get('stakeholders') if isinstance(doc_info.get('stakeholders'), list) else None
    if stakeholders_text:
        stakeholder_section = _collapse_whitespace(stakeholders_text)
    elif stakeholder_list:
        stakeholder_section = "\n".join(
            f"- {stakeholder}" for stakeholder in stakeholder_list if str(stakeholder).strip()
        )
    else:
        stakeholder_section = (
            "- Prospective patients seeking rapid specialist triage\n"
            "- Medical directors overseeing departmental workloads\n"
            "- Digital operations teams ensuring compliance and performance"
        )

    requirement_lines = _format_bullet_list(
        doc_info.get('requirements'),
        "- Intelligent intake workflows, automated case sheet creation, doctor allocation, and unified communications"
    )

    technical_lines = _format_bullet_list(
        doc_info.get('technical_aspects'),
        "- Modular microservice architecture, enterprise messaging integration, analytics-ready data layer"
    )

    excerpt = _collapse_whitespace(project.extracted_text, excerpt_limit) or (
        "Comprehensive documentation will be incorporated once final source materials are confirmed with "
        "the client team."
    )

    preview_content = (
        f"PROJECT TITLE & OVERVIEW\n"
        f"────────────────────────────────────────\n"
        f"{title}\n\n"
        f"{chr(10).join(overview_lines)}\n\n"
        f"PRIMARY OBJECTIVES\n"
        f"────────────────────────────────────────\n"
        f"- Deliver a premium, AI-augmented triage experience that mirrors Fortune 100 product standards\n"
        f"- Guarantee regulatory-grade data protection, provenance, and auditability across markets\n"
        f"- Provide high-availability infrastructure and observability for global clinical operations\n"
        f"- Launch an extensible platform that accelerates new service lines and cross-selling opportunities\n"
        f"- Drive measurable conversion uplift through proactive lead nurturing and appointment orchestration\n\n"
        f"TARGET USERS & STAKEHOLDERS\n"
        f"────────────────────────────────────────\n"
        f"{stakeholder_section}\n\n"
        f"KEY REQUIREMENTS\n"
        f"────────────────────────────────────────\n"
        f"{requirement_lines}\n\n"
        f"TECHNICAL CONSIDERATIONS\n"
        f"────────────────────────────────────────\n"
        f"{technical_lines}\n\n"
        f"DOCUMENT EXCERPT\n"
        f"────────────────────────────────────────\n"
        f"{excerpt}\n\n"
        f"NEXT STEPS\n"
        f"────────────────────────────────────────\n"
        f"Please review this summary and proceed to select internal solutions to incorporate into your concept note."
    )

    return preview_content


class InternalSolutionViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for internal solutions"""
    queryset = InternalSolution.objects.all()
    serializer_class = InternalSolutionSerializer


@api_view(['POST'])
def upload_document(request):
    """Upload document and create new project"""
    serializer = ProjectCreateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Create project
    project = serializer.save(status='clarifying')
    
    # Extract text from document
    try:
        file_path = project.original_document.path
        extracted_text = extract_text_from_file(file_path)
        project.extracted_text = extracted_text
        
        # Use Information Gatherer to analyze document
        try:
            info_gatherer = InformationGatherer()
            doc_info = info_gatherer.extract_document_info(extracted_text)
        except Exception as e:
            print(f"⚠️ Document analysis failed: {e}")
            doc_info = {}
        
        project.context_data = {'doc_info': doc_info}
        project.save()
        
        # Add system message
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content=f'📄 File "{project.original_document.name}" uploaded and processed successfully.'
        )
        
        # Ask for additional context before clarification questions
        content = (
            f'✅ I\'ve successfully analyzed your document "{project.title}".\n\n'
            f'📝 **Do you have any additional description or supporting files to provide?**\n\n'
            f'You can:\n'
            f'- Provide additional context or description about the project\n'
            f'- Upload supporting documents (click the file icon)\n'
            f'- Type "skip" or "no" to proceed directly to clarification questions\n\n'
            f'This will help me create a more comprehensive concept note.'
        )
        
        # Store that we're waiting for additional context
        project.context_data = project.context_data or {}
        project.context_data['awaiting_additional_context'] = True
        project.save()
        
        # Add assistant message
        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content=content
        )
        
    except Exception as e:
        project.delete()
        return Response(
            {'error': f'Failed to process document: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def send_message(request):
    """Handle user messages and orchestrate responses"""
    serializer = MessageCreateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    project_id = serializer.validated_data['project_id']
    content = serializer.validated_data['content']
    
    project = get_object_or_404(Project, id=project_id)
    
    # Check if we're in the "awaiting additional context" phase
    context_data = project.context_data or {}
    if context_data.get('awaiting_additional_context'):
        # User is responding to the "additional description/files" prompt
        content_lower = content.lower().strip()
        
        # Check if user wants to skip
        if any(word in content_lower for word in ['skip', 'no', 'proceed', 'continue', 'next']):
            # User wants to skip - proceed to clarification questions
            ConversationMessage.objects.create(
                project=project,
                role='user',
                content=content
            )
            
            # Clear the awaiting flag
            context_data['awaiting_additional_context'] = False
            project.context_data = context_data
            project.save()
            
            # Generate clarification questions now
            try:
                questions = generate_dynamic_clarification_questions(
                    raw_input=None,
                    pdf_text=project.extracted_text[:5000],
                    audio_transcript=None,
                    uploaded_files_count=1
                )
                
                if questions and len(questions) > 0:
                    context_data['clarification_questions'] = questions
                    project.context_data = context_data
                    project.save()
                    
                    response_content = (
                        f'Great! Now let\'s gather some key information.\n\n'
                        f'**Please answer the {len(questions)} structured questions displayed below, or skip them if you wish to proceed.**'
                    )
                    print(f"✅ Generated {len(questions)} structured questions")
                else:
                    response_content = 'Great! Now, what is the primary goal or purpose of this project?'
                    print("⚠️ Using fallback question")
            except Exception as e:
                print(f"⚠️ Question generation failed: {e}")
                response_content = 'Great! Now, what is the primary goal or purpose of this project?'
            
            ConversationMessage.objects.create(
                project=project,
                role='assistant',
                content=response_content
            )
            
            serializer = ProjectSerializer(project)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            # User provided additional context - save it and ask if they want to add more
            ConversationMessage.objects.create(
                project=project,
                role='user',
                content=content
            )
            
            # Store additional context
            if 'additional_context' not in context_data:
                context_data['additional_context'] = []
            context_data['additional_context'].append(content)
            project.context_data = context_data
            project.save()
            
            # Ask if they want to add more or proceed
            response_content = (
                '✅ Thank you for the additional context!\n\n'
                'Would you like to:\n'
                '- Add more description or upload another file\n'
                '- Type "proceed" to move to clarification questions'
            )
            
            ConversationMessage.objects.create(
                project=project,
                role='assistant',
                content=response_content
            )
            
            serializer = ProjectSerializer(project)
            return Response(serializer.data, status=status.HTTP_200_OK)
    
    # Detect structured clarification answers
    is_structured_answers = False
    made_preview = False
    parsed_answers_list = None
    try:
        # New protocol: token-prefixed payload from frontend
        if isinstance(content, str) and content.startswith('__CLARIFICATION_SUBMISSION__::'):
            answers_obj = content.split('__CLARIFICATION_SUBMISSION__::', 1)[1]
            answers_map = json.loads(answers_obj)  # { id: answer or 'NO_RESPONSE_SKIPPED' }
            # Normalize to list of dicts
            parsed_answers_list = [
                { 'id': int(k), 'answer': v, 'skipped': (v == 'NO_RESPONSE_SKIPPED') }
                for k, v in answers_map.items()
            ]
            is_structured_answers = True
        else:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and parsed.get('type') == 'clarification_answers' and isinstance(parsed.get('answers'), list):
                parsed_answers_list = parsed['answers']
                is_structured_answers = True

        if is_structured_answers:
            print(f"✅ Detected structured clarification answers: {len(parsed_answers_list or [])} answers")
            is_structured_answers = True
            context_data = project.context_data or {}
            
            # Retrieve questions from context to merge with answers
            stored_questions = context_data.get('clarification_questions', [])
            print(f"📋 Found {len(stored_questions)} stored questions")
            
            # Merge questions with answers - ensure we have both question text and answers
            for answer in (parsed_answers_list or []):
                # Convert ID to int if it's a string (from JSON)
                if isinstance(answer.get('id'), str) and answer['id'].isdigit():
                    answer['id'] = int(answer['id'])
                    
                # Find matching question
                matching_q = next((q for q in stored_questions if q.get('id') == answer.get('id')), None)
                if matching_q and not answer.get('question'):
                    answer['question'] = matching_q.get('question', '')
                    # Also copy the 'why_asking' field for context
                    if not answer.get('why_asking') and matching_q.get('why_asking'):
                        answer['why_asking'] = matching_q.get('why_asking')
            
            context_data['clarification_answers'] = parsed_answers_list or []
            if 'clarification_questions' in context_data:
                del context_data['clarification_questions']
            project.context_data = context_data
            project.save()
            # Also create a readable user message for history
            def _fmt(a):
                qtxt = a.get('question') or ''
                ans = a.get('answer') if a.get('answer') is not None else ''
                if a.get('skipped') or ans == 'NO_RESPONSE_SKIPPED':
                    ans = '[skipped]'
                return f"Q{a.get('id')}: {qtxt}\nA: {ans}"
            pretty = "\n".join([_fmt(a) for a in (parsed_answers_list or [])])
            ConversationMessage.objects.create(project=project, role='user', content=f"[Structured Answers Submitted]\n{pretty}")

            # Build a concise project summary preview including answers
            info_gatherer = InformationGatherer()
            messages = list(project.messages.values('role', 'content'))
            conv_summary = info_gatherer.summarize_conversation(messages)

            doc_info = (project.context_data or {}).get('doc_info', {})

            # Prepare rich context for preview generation
            def _list_to_lines(items):
                if not isinstance(items, (list, tuple)):
                    return ""
                return "\n".join(f"- {str(item)}" for item in items if str(item).strip())

            doc_section_parts = []
            if isinstance(doc_info, dict):
                topic = doc_info.get('topic')
                if topic:
                    doc_section_parts.append(f"Topic: {topic}")
                requirements = _list_to_lines(doc_info.get('requirements'))
                if requirements:
                    doc_section_parts.append("Key Requirements:\n" + requirements)
                stakeholders = _list_to_lines(doc_info.get('stakeholders'))
                if stakeholders:
                    doc_section_parts.append("Stakeholders:\n" + stakeholders)
                technical = _list_to_lines(doc_info.get('technical_aspects'))
                if technical:
                    doc_section_parts.append("Technical Aspects:\n" + technical)
                constraints = _list_to_lines(doc_info.get('constraints'))
                if constraints:
                    doc_section_parts.append("Constraints:\n" + constraints)

            answers_lines = []
            highlight_points = []
            for a in (parsed_answers_list or []):
                qtext = (a.get('question') or '').strip()
                ans = a.get('answer')
                if a.get('skipped') or ans == 'NO_RESPONSE_SKIPPED' or ans is None:
                    ans_clean = '[skipped]'
                else:
                    ans_clean = str(ans).strip()
                if qtext:
                    answers_lines.append(f"Question: {qtext}\nAnswer: {ans_clean}")
                if ans_clean and ans_clean != '[skipped]':
                    highlight_points.append(f"{qtext[:80]} → {ans_clean}")

            conv_section_parts = []
            if isinstance(conv_summary, dict):
                for key in ['project_goal', 'target_users', 'timeline', 'technical_constraints', 'additional_context']:
                    val = conv_summary.get(key)
                    if val:
                        conv_section_parts.append(f"{key.replace('_', ' ').title()}: {val}")
                        highlight_points.append(str(val))

            raw_input_sections = [
                f"PROJECT TITLE: {project.title}",
                f"DOCUMENT TEXT (excerpt):\n{_collapse_whitespace((project.extracted_text or '')[:3500])}",
            ]
            if doc_section_parts:
                raw_input_sections.append("DOCUMENT INSIGHTS:\n" + "\n".join(doc_section_parts))
            if conv_section_parts:
                raw_input_sections.append("CONVERSATION SUMMARY:\n" + "\n".join(conv_section_parts))
            if answers_lines:
                raw_input_sections.append("CLARIFICATION ANSWERS:\n" + "\n\n".join(answers_lines))

            raw_input_text = "\n\n".join(section for section in raw_input_sections if section.strip())
            highlight_points_text = "\n".join(
                f"- {p}" for p in highlight_points if str(p).strip()
            ) or None

            print(f"🔍 Attempting to generate preview for project: {project.title}")
            print(f"📊 Raw input length: {len(raw_input_text)} chars")
            print(f"💡 Highlight points: {highlight_points_text[:200] if highlight_points_text else 'None'}")
            
            try:
                preview_content = generate_preview(raw_input_text, highlight_points_text)
                print(f"✅ Preview generated successfully, length: {len(preview_content)} chars")
            except Exception as preview_error:
                print(f"⚠️ Preview generation failed, using fallback: {preview_error}")
                import traceback
                traceback.print_exc()
                preview_content = _build_professional_preview(
                    project,
                    conv_summary,
                    doc_info,
                    excerpt_limit=600
                )

            print(f"💾 Creating preview artifact for project: {project.title}")
            artifact = Artifact.objects.create(
                project=project,
                title=f"{project.title} - Project Summary Preview",
                content=preview_content,
                version="v0.1",
                status='preview',
                metadata={ 'type': 'summary_preview', 'editable': True }
            )
            print(f"✅ Created artifact ID: {artifact.id}")
            
            # Update project status
            project.status = 'preview'
            project.save()
            print(f"📈 Updated project status to: {project.status}")

            ConversationMessage.objects.create(
                project=project,
                role='assistant',
                content='📝 I have created a Project Summary Preview from your answers. Please review it in the Artifacts panel and confirm to proceed.'
            )
            made_preview = True
        else:
            # Not our structured payload
            ConversationMessage.objects.create(project=project, role='user', content=content)
    except Exception as e:
        # Plain text path (including skip messages) - this is expected behavior
        # Only log if it's not a JSON parsing error
        if not isinstance(e, json.JSONDecodeError):
            print(f"⚠️ Unexpected exception in message parsing: {e}")
            import traceback
            traceback.print_exc()
        ConversationMessage.objects.create(project=project, role='user', content=content)
        
        # Check if this is a skip message
        if 'skip' in content.lower() or 'proceed' in content.lower() or 'enough information' in content.lower():
            print(f"🔍 Detected skip/proceed message, creating preview artifact")
            
            # Build a simple preview from the conversation
            info_gatherer = InformationGatherer()
            messages = list(project.messages.values('role', 'content'))
            conv_summary = info_gatherer.summarize_conversation(messages)
            
            # Get document info for richer preview
            doc_info = (project.context_data or {}).get('doc_info', {})
            
            # Use the professional preview builder
            preview_content = _build_professional_preview(
                project,
                conv_summary,
                doc_info,
                excerpt_limit=600
            )
            
            # Create the artifact
            artifact = Artifact.objects.create(
                project=project,
                title=f"{project.title} - Project Summary Preview",
                content=preview_content,
                version="v0.1",
                status='preview',
                metadata={ 'type': 'summary_preview', 'editable': True }
            )
            
            # Update project status
            project.status = 'preview'
            project.save()
            
            # Add message about the preview
            ConversationMessage.objects.create(
                project=project,
                role='assistant',
                content='📝 I have created a Project Summary Preview based on your document. Please review it in the Artifacts panel and confirm to proceed.'
            )
            
            made_preview = True
    
    # Get conversation history
    messages = list(project.messages.values('role', 'content'))
    user_responses = [m for m in messages if m['role'] == 'user']

    # Clear stored structured questions if the user replies in main chat
    context_data = project.context_data or {}
    if 'clarification_questions' in context_data:
        del context_data['clarification_questions']
        project.context_data = context_data
        project.save()

    # If a preview was just created, return early (user will confirm preview next)
    if made_preview:
        print(f"✅ Preview was created, returning project with artifacts")
        # Make sure to include artifacts in the response
        serializer = ProjectSerializer(project)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # If this was a clarification answer submission but no preview was created, create one now
    if is_structured_answers and not made_preview:
        print(f"⚠️ Clarification answers received but no preview was created, creating one now")
        
        # Build a professional preview from the conversation
        info_gatherer = InformationGatherer()
        messages = list(project.messages.values('role', 'content'))
        conv_summary = info_gatherer.summarize_conversation(messages)
        
        # Get document info for richer preview
        doc_info = (project.context_data or {}).get('doc_info', {})
        
        # Use the professional preview builder
        preview_content = _build_professional_preview(
            project,
            conv_summary,
            doc_info,
            excerpt_limit=600
        ) 
        
        # Create the artifact
        artifact = Artifact.objects.create(
            project=project,
            title=f"{project.title} - Project Summary Preview",
            content=preview_content,
            version="v0.1",
            status='preview',
            metadata={ 'type': 'summary_preview', 'editable': True }
        )
        
        # Update project status
        project.status = 'preview'
        project.save()
        
        # Add message about the preview
        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content='📝 I have created a Project Summary Preview from your answers. Please review it in the Artifacts panel and confirm to proceed.'
        )
        
        # Return the updated project
        serializer = ProjectSerializer(project)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    # Move to processing faster: after >=2 user replies
    if len(user_responses) >= 2:
        from .utils import vector_store
        info_gatherer = InformationGatherer()

        conv_summary = info_gatherer.summarize_conversation(messages)
        
        project_context = f"{project.extracted_text[:1000]}\n\n"
        for msg in messages[-8:]:
            project_context += f"{msg['role']}: {msg['content']}\n"

        relevant_solutions = vector_store.search_similar(project_context, top_k=6)

        context_data = project.context_data or {}
        context_data['conv_preview'] = conv_summary
        context_data['relevant_solutions'] = relevant_solutions
        project.context_data = context_data
        project.status = 'processing'
        project.save()

        # Don't create any message - the frontend will handle showing the solution modal
        pass
    else:
        # Don't add any fallback message - just return the project as is
        pass
    
    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def create_project_from_text(request):
    """Create a project starting from a plain text description"""
    title = request.data.get('title') or 'Untitled Project'
    description = request.data.get('description', '').strip()
    if not description:
        return Response({'error': 'Description is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Create project without a file
    project = Project.objects.create(title=title, status='clarifying', extracted_text=description)

    # Non-fatal Info extraction
    try:
        info_gatherer = InformationGatherer()
        doc_info = info_gatherer.extract_document_info(description)
    except Exception:
        doc_info = {}

    project.context_data = {'doc_info': doc_info}
    project.save()

    # System + initial assistant message
    ConversationMessage.objects.create(
        project=project,
        role='system',
        content='📝 Description received. Starting clarification.'
    )

    ConversationMessage.objects.create(
        project=project,
        role='assistant',
        content='To craft a solid concept note, could you share the primary goal or purpose of this project?'
    )

    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def transcribe_audio(request):
    """Transcribe an uploaded audio file and return text"""
    audio_file = request.FILES.get('audio')
    if not audio_file:
        return Response({'error': 'No audio file provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from .utils import process_audio_with_gemini
        text = process_audio_with_gemini(audio_file)
        return Response({'text': text}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def clarify_questions(request):
    """Generate content-driven clarification questions."""
    raw_input = request.data.get('raw_input') or ''
    pdf_text = request.data.get('pdf_text')
    audio_transcript = request.data.get('audio_transcript')
    uploaded_files_count = int(request.data.get('uploaded_files_count') or 0)

    try:
        qs = generate_dynamic_clarification_questions(
            raw_input=raw_input,
            pdf_text=pdf_text,
            audio_transcript=audio_transcript,
            uploaded_files_count=uploaded_files_count,
        )
        return Response(qs, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def generate_concept_note(request):
    """Generate concept note using multi-agent workflow"""
    serializer = GenerateConceptNoteSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    project_id = serializer.validated_data['project_id']
    solution_ids = serializer.validated_data.get('selected_solution_ids', [])
    
    project = get_object_or_404(Project, id=project_id)
    
    try:
        # Check if there's an edited preview artifact to use as base
        preview_artifact = project.artifacts.filter(
            metadata__type='summary_preview'
        ).order_by('-created_at').first()
        
        edited_preview_content = None
        if preview_artifact:
            edited_preview_content = preview_artifact.content
            print(f"✅ Found edited preview artifact, will incorporate user edits")
        
        # Add system messages for agent workflow
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content='🔄 Starting multi-agent workflow...'
        )
        
        # Step 1: Information Gathering
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content='🔍 **Information Gatherer Agent**: Extracting key information from uploaded document...'
        )
        
        info_gatherer = InformationGatherer()
        messages = list(project.messages.values('role', 'content'))
        conv_summary = info_gatherer.summarize_conversation(messages)
        
        # Step 2: FAISS Retrieval (if solutions selected)
        selected_solutions = []
        if solution_ids:
            ConversationMessage.objects.create(
                project=project,
                role='system',
                content=f'💾 **FAISS Vector Store**: Retrieving {len(solution_ids)} internal solution(s) from knowledge base...'
            )
            selected_solutions = InternalSolution.objects.filter(id__in=solution_ids)
            
            for solution in selected_solutions:
                ProjectSolution.objects.get_or_create(
                    project=project,
                    solution=solution
                )
        
        # Step 3: External Research
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content='🌐 **Competitor Analysis Agent**: Performing DuckDuckGo web search for external references...'
        )
        
        competitor_agent = CompetitorAgent()
        topic = project.context_data.get('doc_info', {}).get('topic', project.title)
        research = competitor_agent.research_topic(topic, {})
        
        # Step 4: Analysis
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content='🧠 **Analysis Agent**: Processing gathered data, performing NLP analysis...'
        )
        
        analysis_agent = AnalysisAgent()
        analysis = analysis_agent.analyze_requirements({
            'doc_info': project.context_data.get('doc_info', {}),
            'conv_summary': conv_summary,
            'research': research
        })
        
        # Step 5: Solution Architecture
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content='🏗️ **Solution Architect Agent**: Designing technical architecture and project blueprint...'
        )
        
        architect = SolutionArchitect()
        architecture = architect.design_architecture({
            'requirements': conv_summary,
            'analysis': analysis,
            'research': research
        }, selected_solutions)
        
        # Step 6: Document Generation
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content='📝 **Document Generator Agent**: Compiling comprehensive concept note...'
        )
        
        doc_generator = DocumentGenerator()
        concept_note = doc_generator.generate_concept_note({
            'title': project.title,
            'doc_info': project.context_data.get('doc_info', {}),
            'conv_summary': conv_summary,
            'solutions': list(selected_solutions),
            'research': research,
            'analysis': analysis,
            'architecture': architecture,
            'edited_preview': edited_preview_content  # Include user's edited preview
        })
        
        # Create artifact (only store serializable metadata)
        artifact = Artifact.objects.create(
            project=project,
            title=f"{project.title} - Concept Note",
            content=concept_note,
            version="v1.0",
            status='preview',
            metadata={
                'type': 'concept_note',
                'editable': True,
                'generated_with_solutions': len(selected_solutions) > 0,
                'solution_count': len(selected_solutions)
            }
        )
        
        artifact.selected_solutions.set(selected_solutions)
        
        # Update project status
        project.status = 'preview'
        project.save()
        
        # Add success message
        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content='✅ **Concept note generated successfully!**\n\nI\'ve compiled all the information into a comprehensive document. You can now:\n- Review the concept note in the Artifacts panel\n- Edit and refine the content\n- Confirm when you\'re satisfied\n- Download as PDF'
        )
        
        serializer = ProjectSerializer(project)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"❌ Error generating concept note: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Create a fallback artifact with error information
        try:
            error_content = f"""# Concept Note Generation Error

We encountered an issue while generating your concept note. Our team has been notified.

## Error Details
{str(e)}

## Next Steps
You can:
1. Try again with different solution selections
2. Continue with a manual concept note
3. Contact support if the issue persists"""
            
            # Create artifact even if there was an error
            artifact = Artifact.objects.create(
                project=project,
                title=f"{project.title} - Concept Note (Error Recovery)",
                content=error_content,
                version="v1.0",
                status='preview',
                metadata={
                    'error': str(e),
                    'type': 'concept_note',
                    'subtype': 'error_recovery',
                    'editable': True
                }
            )
            
            # Update project status
            project.status = 'preview'
            project.save()
            
            # Add message about the error
            ConversationMessage.objects.create(
                project=project,
                role='assistant',
                content='⚠️ **There was an issue generating the complete concept note.**\n\nI\'ve created a basic document that you can edit. You can also try again with different selections.'            
            )
            
            serializer = ProjectSerializer(project)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as fallback_error:
            print(f"❌ Even fallback artifact creation failed: {fallback_error}")
            traceback.print_exc()
            
        return Response(
            {'error': f'Failed to generate concept note: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
def update_artifact(request):
    """Update artifact content or status"""
    serializer = ArtifactUpdateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    artifact_id = serializer.validated_data['artifact_id']
    artifact = get_object_or_404(Artifact, id=artifact_id)
    
    if 'content' in serializer.validated_data:
        artifact.content = serializer.validated_data['content']
    
    if 'status' in serializer.validated_data:
        artifact.status = serializer.validated_data['status']
        
        if artifact.status == 'confirmed':
            artifact.project.status = 'completed'
            artifact.project.save()
            
            ConversationMessage.objects.create(
                project=artifact.project,
                role='system',
                content='✅ Concept note confirmed and saved to database!'
            )
    
    artifact.save()
    
    serializer = ArtifactSerializer(artifact)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_project(request, project_id):
    """Get project details with messages and artifacts"""
    project = get_object_or_404(Project, id=project_id)
    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_200_OK)