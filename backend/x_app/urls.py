# x_app/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'solutions', views.InternalSolutionViewSet, basename='solutions')

urlpatterns = [
    # DRF router endpoints (e.g., /api/solutions/)
    path('', include(router.urls)),

    # Project + chat
    path('project/from-text/', views.create_project_from_text, name='create-project-from-text'),
    path('project/<int:project_id>/', views.get_project, name='get-project'),
    path('message/', views.send_message, name='send-message'),

    # Uploads (support BOTH URLs)
    path('upload/', views.upload_document, name='upload-document'),           # existing
    path('upload-document/', views.upload_document, name='upload-document'),  # new for frontend

    # Concept note + artifacts
    path('generate/', views.generate_concept_note, name='generate-concept-note'),
    path('artifact/update/', views.update_artifact, name='update-artifact'),

    # Clarification Qs
    path('clarify-questions/', views.clarify_questions, name='clarify-questions'),

    # Audio transcription (single entry only)
    path('transcribe/', views.transcribe_audio, name='transcribe-audio'),
]
