import api from '../api/axios';

export async function register(username, password) {
  const response = await api.post('/auth/register', { username, password });
  return response.data;
}

export async function login(username, password) {
  const response = await api.post('/auth/login', { username, password });
  return response.data;
}
