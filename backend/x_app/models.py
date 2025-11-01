from django.db import models
from django.contrib.auth.models import User


class InternalSolution(models.Model):
    """Stores reusable internal solutions for FAISS retrieval"""
    name = models.CharField(max_length=200)
    description = models.TextField()
    technical_stack = models.JSONField(default=dict, blank=True)
    features = models.JSONField(default=list, blank=True)
    documentation = models.TextField(blank=True)
    embedding = models.JSONField(default=list, blank=True)  # Store embeddings
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'internal_solutions'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class Project(models.Model):
    """Main project entity"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('clarifying', 'Clarifying'),
        ('processing', 'Processing'),
        ('preview', 'Preview'),
        ('completed', 'Completed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=300)
    original_document = models.FileField(upload_to='documents/')
    extracted_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    context_data = models.JSONField(default=dict, blank=True)  # Store Q&A context
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class ConversationMessage(models.Model):
    """Stores conversation history"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'conversation_messages'
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class Artifact(models.Model):
    """Stores generated concept notes with versioning"""
    STATUS_CHOICES = [
        ('preview', 'Preview'),
        ('confirmed', 'Confirmed'),
    ]
    
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='artifacts'
    )
    title = models.CharField(max_length=300)
    content = models.TextField()
    version = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preview')
    metadata = models.JSONField(default=dict, blank=True)  # Store agent insights
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'artifacts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.version}"


class ProjectSolution(models.Model):
    """Many-to-many relationship between projects and internal solutions"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    solution = models.ForeignKey(InternalSolution, on_delete=models.CASCADE)
    relevance_score = models.FloatField(default=0.0)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'project_solutions'
        unique_together = ['project', 'solution']
        ordering = ['-relevance_score']
    
    def __str__(self):
        return f"{self.project.title} - {self.solution.name}"