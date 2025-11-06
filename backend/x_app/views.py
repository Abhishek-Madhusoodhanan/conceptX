# x_app/views.py  — final

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

import json

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
from .utils import extract_text_from_file
from .agent import (
    ReActExecutor,
    generate_dynamic_clarification_questions,
)

# =============================== Agent (singleton) ===============================

_GLOBAL_ORCHESTRATOR = None

def get_orchestrator():
    global _GLOBAL_ORCHESTRATOR
    if _GLOBAL_ORCHESTRATOR is None:
        _GLOBAL_ORCHESTRATOR = ReActExecutor()
    return _GLOBAL_ORCHESTRATOR


# ================================ ViewSets ======================================

class InternalSolutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InternalSolution.objects.all()
    serializer_class = InternalSolutionSerializer


# ============================== Utility helpers =================================

def _create_preview_artifact(project, agent_result):
    """Create or update a 'summary_preview' artifact from agent response."""
    try:
        preview_content = agent_result.get('response', '') or ''
        existing = project.artifacts.filter(metadata__type='summary_preview').first()

        if existing:
            existing.content = preview_content
            existing.save()
        else:
            Artifact.objects.create(
                project=project,
                title=f"{project.title} - Project Summary Preview",
                content=preview_content,
                version="v0.1",
                status='preview',
                metadata={'type': 'summary_preview', 'editable': True},
            )

        project.status = 'preview'
        project.save(update_fields=['status'])
    except Exception as e:
        print(f"❌ Error creating preview artifact: {e}")


def _create_concept_note_artifact(project, agent_result):
    """Create a 'concept_note' artifact from agent response."""
    try:
        concept_note_content = agent_result.get('response', '') or ''
        Artifact.objects.create(
            project=project,
            title=f"{project.title} - Concept Note",
            content=concept_note_content,
            version="v1.0",
            status='preview',
            metadata={'type': 'concept_note', 'editable': True},
        )
        project.status = 'preview'
        project.save(update_fields=['status'])
    except Exception as e:
        print(f"❌ Error creating concept note artifact: {e}")


# ============================== API Endpoints ===================================

@api_view(['POST'])
def transcribe_audio(request):
    """
    Transcribe an uploaded audio file and return text.
    Accepts field name 'audio' or 'file'.
    """
    audio_file = request.FILES.get('audio') or request.FILES.get('file')
    if not audio_file:
        return Response({'error': 'No audio file provided'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        from .utils import process_audio_with_gemini
        text = process_audio_with_gemini(audio_file)
        return Response({'text': text}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def upload_document(request):
    """
    Upload document.
    - If `project_id` is provided: attach to existing project and keep chat history.
    - Else: create a new project (legacy path) with the uploaded file.
    """
    project_id = request.data.get('project_id')

    # ---------------- Attach to existing project ----------------
    if project_id:
        project = get_object_or_404(Project, id=project_id)
        file = request.FILES.get('file') or request.FILES.get('document') or request.FILES.get('original_document')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Save the new file onto the existing project
        project.original_document = file
        project.save(update_fields=['original_document'])

        try:
            file_path = project.original_document.path
            extracted_text = extract_text_from_file(file_path)

            # Append new text to existing extracted_text with separator
            project.extracted_text = (project.extracted_text or '') + ("\n\n" if project.extracted_text else '') + extracted_text
            project.save(update_fields=['extracted_text'])

            # System message for UI
            ConversationMessage.objects.create(
                project=project,
                role='system',
                content=f'📄 File "{project.original_document.name}" uploaded and processed successfully.'
            )

            # Let the agent respond to the new context with a single best next question
            orchestrator = get_orchestrator()
            context = {
                'document_text': project.extracted_text,
                'project_title': project.title,
                'stage': 'document_appended'
            }
            result = orchestrator.process_user_input(
                "A new document was added. Analyze it and ask me only one next best question.",
                project,
                context
            )
            ConversationMessage.objects.create(project=project, role='assistant', content=result['response'])

        except Exception as e:
            return Response({'error': f'Failed to process document: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ProjectSerializer(project)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ---------------- Create a new project from uploaded file ----------------
    serializer = ProjectCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project = serializer.save(status='clarifying')

    try:
        file_path = project.original_document.path
        extracted_text = extract_text_from_file(file_path)
        project.extracted_text = extracted_text
        project.save(update_fields=['extracted_text'])

        ConversationMessage.objects.create(
            project=project,
            role='system',
            content=f'📄 File "{project.original_document.name}" uploaded and processed successfully.'
        )

        orchestrator = get_orchestrator()
        context = {'document_text': extracted_text, 'project_title': project.title, 'stage': 'initial_upload'}
        result = orchestrator.process_user_input(
            f"I've uploaded a document titled '{project.title}'. Please analyze it and ask relevant questions.",
            project,
            context
        )
        ConversationMessage.objects.create(project=project, role='assistant', content=result['response'])

    except Exception as e:
        project.delete()
        return Response({'error': f'Failed to process document: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def create_project_from_text(request):
    """
    Create a project starting from plain text.
    If the text is a greeting/very short, respond like a chatbot (no 'analysis' system message).
    """
    title = request.data.get('title') or 'Untitled Project'
    description = (request.data.get('description') or '').strip()
    if not description:
        return Response({'error': 'Description is required'}, status=status.HTTP_400_BAD_REQUEST)

    project = Project.objects.create(
        title=title,
        status='clarifying',
        extracted_text=description
    )

    lower = description.lower()
    is_greeting = (
        lower in {"hi", "hello", "hey", "yo", "hola", "sup"} or
        lower.startswith(("hi ", "hello ", "hey ")) or
        (len(description.split()) < 3 and "?" not in description)
    )

    if not is_greeting:
        ConversationMessage.objects.create(
            project=project, role='system',
            content='📝 Description received. Starting analysis.'
        )

    # Save the first user message so the thread isn’t empty
    ConversationMessage.objects.create(project=project, role='user', content=description)

    orchestrator = get_orchestrator()
    context = {'document_text': description, 'project_title': title, 'stage': 'initial_text'}

    if is_greeting:
        result = orchestrator.process_user_input(description, project, context)
    else:
        result = orchestrator.process_user_input(
            f"I'm starting a project called '{title}'. Here's my initial description: {description}",
            project,
            context
        )

    ConversationMessage.objects.create(project=project, role='assistant', content=result['response'])
    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def send_message(request):
    """
    Main chat endpoint: routes user messages through the ReAct agent with current project context.
    """
    serializer = MessageCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project_id = serializer.validated_data['project_id']
    content = serializer.validated_data['content']
    project = get_object_or_404(Project, id=project_id)

    ConversationMessage.objects.create(project=project, role='user', content=content)

    try:
        orchestrator = get_orchestrator()
        context = {
            'document_text': project.extracted_text,
            'project_title': project.title,
            'stage': project.status,
            'context_data': project.context_data or {},
            'conversation_history': list(project.messages.values('role', 'content')),
        }

        result = orchestrator.process_user_input(content, project, context)

        ConversationMessage.objects.create(project=project, role='assistant', content=result['response'])

        # Optional actions from the agent
        if result.get('actions'):
            for action in result['actions']:
                t = action.get('type')
                if t == 'show_solutions':
                    project.status = 'processing'
                    project.save(update_fields=['status'])
                elif t == 'show_preview':
                    _create_preview_artifact(project, result)
                elif t == 'show_concept_note':
                    _create_concept_note_artifact(project, result)

        out = ProjectSerializer(project)
        return Response(out.data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ Error in send_message: {e}")
        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content="I hit an issue processing that. Could you rephrase or share a bit more detail?"
        )
        out = ProjectSerializer(project)
        return Response(out.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def clarify_questions(request):
    """
    Generate content-driven clarification questions (3–5) from mixed inputs.
    """
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
    """
    Generate concept note using the ReAct agent and selected internal solutions.
    """
    serializer = GenerateConceptNoteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project_id = serializer.validated_data['project_id']
    solution_ids = serializer.validated_data.get('selected_solution_ids', [])

    project = get_object_or_404(Project, id=project_id)

    try:
        selected_solutions = InternalSolution.objects.filter(id__in=solution_ids)

        orchestrator = get_orchestrator()
        context = {
            'document_text': project.extracted_text,
            'project_title': project.title,
            'stage': 'concept_note_generation',
            'selected_solutions': [
                {'name': s.name, 'description': s.description, 'features': s.features}
                for s in selected_solutions
            ],
            'conversation_history': list(project.messages.values('role', 'content')),
        }

        result = orchestrator.process_user_input(
            f"Generate a comprehensive concept note for this project, incorporating these internal solutions: "
            f"{', '.join([s.name for s in selected_solutions])}",
            project,
            context
        )

        artifact = Artifact.objects.create(
            project=project,
            title=f"{project.title} - Concept Note",
            content=result['response'],
            version="v1.0",
            status='preview',
            metadata={
                'type': 'concept_note',
                'editable': True,
                'generated_with_solutions': True,
                'solution_count': len(selected_solutions),
            },
        )

        for s in selected_solutions:
            ProjectSolution.objects.get_or_create(project=project, solution=s)

        project.status = 'preview'
        project.save(update_fields=['status'])

        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content=(
                "✅ **Concept note generated successfully!**\n\n"
                "You can now:\n- Review it in the Artifacts panel\n- Edit and refine\n"
                "- Confirm when satisfied\n- Download as PDF"
            )
        )

        out = ProjectSerializer(project)
        return Response(out.data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ Error generating concept note: {str(e)}")
        return Response({'error': f'Failed to generate concept note: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_artifact(request):
    """
    Update artifact content or status. Confirming a concept note marks project completed.
    """
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
            artifact.project.save(update_fields=['status'])
            ConversationMessage.objects.create(
                project=artifact.project,
                role='system',
                content='✅ Concept note confirmed and saved to database!'
            )

    artifact.save()
    out = ArtifactSerializer(artifact)
    return Response(out.data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_project(request, project_id):
    """Return project details with messages and artifacts."""
    project = get_object_or_404(Project, id=project_id)
    out = ProjectSerializer(project)
    return Response(out.data, status=status.HTTP_200_OK)
