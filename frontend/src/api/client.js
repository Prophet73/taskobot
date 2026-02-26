import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = (code) => api.post('/auth/login', { code });
export const getMe = () => api.get('/auth/me');

// Dashboard
export const getDashboard = () => api.get('/dashboard');

// Projects
export const getProjects = () => api.get('/projects');
export const getProject = (id) => api.get(`/projects/${id}`);
export const getProjectStats = (id) => api.get(`/projects/${id}/stats`);
export const getProjectMembers = (id) => api.get(`/projects/${id}/members`);
export const addProjectMember = (id, data) => api.post(`/projects/${id}/members`, data);
export const removeProjectMember = (projectId, userId) => api.delete(`/projects/${projectId}/members/${userId}`);
export const updateMemberRole = (projectId, userId, data) => api.patch(`/projects/${projectId}/members/${userId}`, data);

// Tasks
export const getTasks = (params = {}) => api.get('/tasks', { params });
export const getMyTasks = (params = {}) => api.get('/tasks/my', { params });
export const getTask = (id) => api.get(`/tasks/${id}`);
export const createTask = (data) => api.post('/tasks', data);
export const updateTask = (id, data) => api.patch(`/tasks/${id}`, data);
export const deleteTask = (id) => api.delete(`/tasks/${id}`);

// Reminders
export const sendReminders = (projectId, userId = null) =>
  api.post('/reminders/send', { project_id: projectId, user_id: userId });

// Comments
export const getTaskComments = (taskId) => api.get(`/tasks/${taskId}/comments`);
export const addTaskComment = (taskId, text) => api.post(`/tasks/${taskId}/comments`, { text });
export const deleteComment = (commentId) => api.delete(`/comments/${commentId}`);

// Task History
export const getTaskHistory = (taskId) => api.get(`/tasks/${taskId}/history`);

// Project Settings
export const updateProjectSettings = (projectId, data) => api.patch(`/projects/${projectId}/settings`, data);
export const generateProjectToken = (projectId) => api.post(`/projects/${projectId}/token`);

// Project Tokens (role-based)
export const createProjectToken = (projectId, role, memberId = null) =>
  api.post(`/projects/${projectId}/tokens`, { role, member_id: memberId });
export const getProjectTokens = (projectId) => api.get(`/projects/${projectId}/tokens`);
export const revokeProjectToken = (projectId, tokenId) => api.delete(`/projects/${projectId}/tokens/${tokenId}`);

// Project by Token (isolated access)
export const getProjectByToken = (token) => api.get('/project-by-token', { params: { token } });

// Token-auth task actions (public, no JWT needed)
export const updateTaskByToken = (token, taskId, data) => api.patch(`/token-tasks/${taskId}`, data, { params: { token } });

// WebApp Auth
export const webappLogin = (initData) => api.post('/auth/webapp', { init_data: initData });

export default api;
