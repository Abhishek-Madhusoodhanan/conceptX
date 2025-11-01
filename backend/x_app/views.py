from django.shortcuts import render

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
from .utils import extract_text_from_file
from .agent import (
    OrchestratorAgent, InformationGatherer, AnalysisAgent,
    SolutionArchitect, CompetitorAgent, DocumentGenerator
)


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
        info_gatherer = InformationGatherer()
        doc_info = info_gatherer.extract_document_info(extracted_text)
        project.context_data = {'doc_info': doc_info}
        project.save()
        
        # Add system message
        ConversationMessage.objects.create(
            project=project,
            role='system',
            content=f'📄 File "{project.original_document.name}" uploaded successfully.'
        )
        
        # Add initial assistant message
        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content=f'I\'ve analyzed your document "{project.title}". To create a comprehensive concept note, I need to gather some information:\n\n**What is the primary goal or purpose of this project?**'
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
    
    # Save user message
    ConversationMessage.objects.create(
        project=project,
        role='user',
        content=content
    )
    
    # Get conversation history
    messages = list(project.messages.values('role', 'content'))
    user_responses = [m for m in messages if m['role'] == 'user']
    
    if len(user_responses) < 4:
        # Continue asking clarification questions
        next_questions = [
            "Great! Now, **who are the target users** or stakeholders for this project?",
            "Perfect. **What is your expected timeline** for this project? (e.g., 2 months, 6 weeks)",
            "Excellent! One last question: **Are there any specific technical constraints** or preferred technologies? (Or just say \"no constraints\")",
            "✅ Thank you! I have all the information needed.\n\nWould you like to select any **internal solutions** from our knowledge base to incorporate into this project?"
        ]
        
        response_content = next_questions[len(user_responses) - 1]
        
        ConversationMessage.objects.create(
            project=project,
            role='assistant',
            content=response_content
        )
        
        if len(user_responses) >= 4:
            project.status = 'processing'
            project.save()
    
    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_200_OK)


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
            'architecture': architecture
        })
        
        # Create artifact
        artifact = Artifact.objects.create(
            project=project,
            title=f"{project.title} - Concept Note",
            content=concept_note,
            version="v1.0",
            status='preview',
            metadata={
                'research': research,
                'analysis': analysis,
                'architecture': architecture
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