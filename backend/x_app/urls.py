# x_app/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'solutions', views.InternalSolutionViewSet, basename='solution')

urlpatterns = [
    path('', include(router.urls)),
    path('upload/', views.upload_document, name='upload-document'),
    path('message/', views.send_message, name='send-message'),
    path('generate/', views.generate_concept_note, name='generate-concept-note'),
    path('artifact/update/', views.update_artifact, name='update-artifact'),
    path('project/<int:project_id>/', views.get_project, name='get-project'),
]