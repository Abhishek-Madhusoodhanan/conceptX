import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const uploadDocument = async (file, title) => {
  const formData = new FormData();
  formData.append('original_document', file);
  formData.append('title', title);

  const response = await axios.post(`${API_BASE_URL}/upload/`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
};

export const sendMessage = async (projectId, content) => {
  const response = await api.post('/message/', {
    project_id: projectId,
    content: content,
  });
  return response.data;
};

export const getInternalSolutions = async () => {
  const response = await api.get('/solutions/');
  return response.data;
};

export const generateConceptNote = async (projectId, selectedSolutionIds) => {
  const response = await api.post('/generate/', {
    project_id: projectId,
    selected_solution_ids: selectedSolutionIds,
  });
  return response.data;
};

export const updateArtifact = async (artifactId, updates) => {
  const response = await api.put('/artifact/update/', {
    artifact_id: artifactId,
    ...updates,
  });
  return response.data;
};

export const getProject = async (projectId) => {
  const response = await api.get(`/project/${projectId}/`);
  return response.data;
};

export default api;