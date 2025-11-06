// src/services/api.js
import axios from "axios";

const API_BASE_URL = "http://localhost:8000/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// ✅ Upload document (NEW PROJECT)
export const uploadDocument = async (file, title) => {
  const formData = new FormData();
  formData.append("original_document", file); // matches ProjectCreateSerializer
  formData.append("title", title);

  const response = await axios.post(`${API_BASE_URL}/upload-document/`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

// ✅ Upload document to existing project (ATTACH)
export const uploadDocumentToProject = async (projectId, file) => {
  const formData = new FormData();
  formData.append("project_id", projectId);
  formData.append("file", file); // matches views.py: 'file' or 'document'

  const response = await axios.post(`${API_BASE_URL}/upload-document/`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

// ✅ Create project from text
export const createProjectFromText = async (title, description) => {
  const response = await api.post("/project/from-text/", { title, description });
  return response.data;
};

// ✅ Send chat message
export const sendMessage = async (projectId, content) => {
  const response = await api.post("/message/", {
    project_id: projectId,
    content,
  });
  return response.data;
};

// ✅ Get internal solutions
export const getInternalSolutions = async () => {
  const response = await api.get("/solutions/");
  return response.data;
};

// ✅ Generate concept note
export const generateConceptNote = async (projectId, selectedSolutionIds) => {
  const response = await api.post("/generate/", {
    project_id: projectId,
    selected_solution_ids: selectedSolutionIds,
  });
  return response.data;
};

// ✅ Update artifact
export const updateArtifact = async (artifactId, updates) => {
  const response = await api.put("/artifact/update/", {
    artifact_id: artifactId,
    ...updates,
  });
  return response.data;
};

// ✅ Get project details
export const getProject = async (projectId) => {
  const response = await api.get(`/project/${projectId}/`);
  return response.data;
};

// ✅ Transcribe audio
export const transcribeAudio = async (file) => {
  const formData = new FormData();
  formData.append("audio", file);
  const response = await axios.post(`${API_BASE_URL}/transcribe/`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export default api;
