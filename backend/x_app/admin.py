# x_app/admin.py
from django.contrib import admin
from .models import (
    InternalSolution,
    Project,
    ConversationMessage,
    Artifact,
    ProjectSolution
)


@admin.register(InternalSolution)
class InternalSolutionAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['created_at']


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title']


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ['project', 'role', 'timestamp']
    list_filter = ['role', 'timestamp']


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ['title', 'version', 'status', 'created_at']
    list_filter = ['status', 'created_at']


@admin.register(ProjectSolution)
class ProjectSolutionAdmin(admin.ModelAdmin):
    list_display = ['project', 'solution', 'relevance_score']


# x_app/management/commands/seed_solutions.py
# Create this file: x_app/management/commands/seed_solutions.py

import os
import django

# First create the directory structure:
# mkdir -p x_app/management/commands
# touch x_app/management/__init__.py
# touch x_app/management/commands/__init__.py

from django.core.management.base import BaseCommand
from x_app.models import InternalSolution


class Command(BaseCommand):
    help = 'Seed database with initial internal solutions'

    def handle(self, *args, **kwargs):
        solutions = [
            {
                'name': 'E-Commerce Platform',
                'description': 'Microservices-based e-commerce system with React frontend, Django backend, Redis caching, and Stripe integration.',
                'technical_stack': {
                    'frontend': ['React', 'Redux', 'Tailwind CSS'],
                    'backend': ['Django', 'Django REST Framework', 'Celery'],
                    'database': ['PostgreSQL', 'Redis'],
                    'payment': ['Stripe API'],
                    'deployment': ['Docker', 'Kubernetes', 'AWS']
                },
                'features': [
                    'Product catalog with search',
                    'Shopping cart and checkout',
                    'Payment processing',
                    'Order management',
                    'User authentication',
                    'Admin dashboard'
                ],
                'documentation': 'Complete e-commerce solution with proven scalability up to 10k concurrent users.'
            },
            {
                'name': 'AI Chat System',
                'description': 'Real-time chat application with LangChain agents, WebSocket support, and conversation memory.',
                'technical_stack': {
                    'frontend': ['React', 'Socket.io-client'],
                    'backend': ['Django', 'Django Channels', 'LangChain'],
                    'ai': ['OpenAI API', 'Gemini API', 'FAISS'],
                    'database': ['PostgreSQL', 'Redis'],
                    'deployment': ['Docker', 'AWS ECS']
                },
                'features': [
                    'Real-time messaging',
                    'AI-powered responses',
                    'Conversation history',
                    'Multi-user support',
                    'File sharing',
                    'Typing indicators'
                ],
                'documentation': 'Enterprise-grade chat system with AI capabilities and 99.9% uptime.'
            },
            {
                'name': 'Document Management System',
                'description': 'Enterprise document management with OCR, versioning, FAISS vector search, and collaborative editing.',
                'technical_stack': {
                    'frontend': ['React', 'Draft.js', 'PDF.js'],
                    'backend': ['Django', 'Celery', 'Tesseract OCR'],
                    'ai': ['FAISS', 'sentence-transformers'],
                    'storage': ['AWS S3', 'PostgreSQL'],
                    'search': ['Elasticsearch']
                },
                'features': [
                    'Document upload and storage',
                    'OCR for scanned documents',
                    'Version control',
                    'Semantic search',
                    'Collaborative editing',
                    'Access control'
                ],
                'documentation': 'Handles 1M+ documents with intelligent search and retrieval.'
            },
            {
                'name': 'Analytics Dashboard',
                'description': 'Real-time analytics platform using Django Channels, React with D3.js, and time-series data processing.',
                'technical_stack': {
                    'frontend': ['React', 'D3.js', 'Recharts', 'WebSocket'],
                    'backend': ['Django', 'Django Channels', 'Pandas'],
                    'database': ['PostgreSQL', 'TimescaleDB', 'Redis'],
                    'processing': ['Apache Kafka', 'Celery'],
                    'deployment': ['Docker', 'Kubernetes']
                },
                'features': [
                    'Real-time data visualization',
                    'Custom dashboard builder',
                    'Multiple chart types',
                    'Data export',
                    'Automated reports',
                    'Alert notifications'
                ],
                'documentation': 'Processes 100k events/second with sub-second visualization updates.'
            },
            {
                'name': 'Project Management Suite',
                'description': 'Comprehensive project management with Gantt charts, resource allocation, and team collaboration.',
                'technical_stack': {
                    'frontend': ['React', 'DHTMLX Gantt', 'React DnD'],
                    'backend': ['Django', 'Django REST Framework'],
                    'database': ['PostgreSQL'],
                    'realtime': ['Django Channels', 'Redis'],
                    'notifications': ['Celery', 'SendGrid']
                },
                'features': [
                    'Project planning with Gantt',
                    'Task management',
                    'Resource allocation',
                    'Time tracking',
                    'Team collaboration',
                    'Reporting and analytics'
                ],
                'documentation': 'Trusted by 500+ teams for managing complex projects.'
            },
            {
                'name': 'CRM System',
                'description': 'Customer Relationship Management with lead tracking, sales pipeline, and email integration.',
                'technical_stack': {
                    'frontend': ['React', 'Material-UI'],
                    'backend': ['Django', 'Django REST Framework'],
                    'database': ['PostgreSQL'],
                    'integration': ['SendGrid API', 'Twilio API'],
                    'automation': ['Celery', 'Redis']
                },
                'features': [
                    'Lead management',
                    'Sales pipeline',
                    'Email integration',
                    'Contact management',
                    'Task automation',
                    'Reports and insights'
                ],
                'documentation': 'Increases sales team productivity by 40%.'
            }
        ]

        for sol_data in solutions:
            solution, created = InternalSolution.objects.get_or_create(
                name=sol_data['name'],
                defaults=sol_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created: {solution.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Already exists: {solution.name}')
                )

        self.stdout.write(
            self.style.SUCCESS('Successfully seeded internal solutions!')
        )