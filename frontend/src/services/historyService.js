import api from '../api/axios';

export async function listHistory({ page = 1, limit = 5 } = {}) {
  const response = await api.get('/history', {
    params: { page, limit },
  });
  return response.data;
}

export async function searchHistory(keyword, { page = 1, limit = 5 } = {}) {
  const response = await api.get('/history/search', {
    params: { q: keyword, page, limit },
  });
  return response.data;
}

export async function getHistoryDetail(identifier) {
  const response = await api.get(`/history/${identifier}`);
  return response.data;
}

export async function renameJob(jobId, newName) {
  const response = await api.put(`/history/${jobId}/rename`, {
    new_name: newName,
  });
  return response.data;
}

export async function deleteJob({ jobId, displayName } = {}) {
  const params = {};
  if (jobId) params.job_id = jobId;
  if (displayName) params.display_name = displayName;

  await api.delete('/history', { params });
}
