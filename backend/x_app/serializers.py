from rest_framework import serializers
from .models import (
    InternalSolution,
    Project,
    ConversationMessage,
    Artifact,
    ProjectSolution
)


class InternalSolutionSerializer(serializers.ModelSerializer):
    relevance_score = serializers.FloatField(required=False, read_only=True)
    
    class Meta:
        model = InternalSolution
        fields = [
            'id', 'name', 'description', 'technical_stack',
            'features', 'documentation', 'created_at', 'relevance_score'
        ]
        read_only_fields = ['id', 'created_at']


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ['id', 'role', 'content', 'timestamp']
        read_only_fields = ['id', 'timestamp']


class ArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact
        fields = [
            'id', 'title', 'content', 'version', 
            'status', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ProjectSerializer(serializers.ModelSerializer):
    messages = ConversationMessageSerializer(many=True, read_only=True)
    artifacts = ArtifactSerializer(many=True, read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'id', 'title', 'original_document', 'extracted_text',
            'status', 'context_data', 'messages', 'artifacts',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['title', 'original_document']
    
    def create(self, validated_data):
        # Extract text from document will be handled in view
        return super().create(validated_data)


class MessageCreateSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()
    content = serializers.CharField()
    
    def validate_project_id(self, value):
        if not Project.objects.filter(id=value).exists():
            raise serializers.ValidationError("Project not found")
        return value


class GenerateConceptNoteSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()
    selected_solution_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list
    )
    
    def validate_project_id(self, value):
        if not Project.objects.filter(id=value).exists():
            raise serializers.ValidationError("Project not found")
        return value


class ArtifactUpdateSerializer(serializers.Serializer):
    artifact_id = serializers.IntegerField()
    content = serializers.CharField(required=False)
    status = serializers.ChoiceField(
        choices=['preview', 'confirmed'],
        required=False
    )
    
    def validate_artifact_id(self, value):
        if not Artifact.objects.filter(id=value).exists():
            raise serializers.ValidationError("Artifact not found")
        return value