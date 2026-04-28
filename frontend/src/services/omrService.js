import api from '../api/axios';

export async function submitOMR(file, wait = false, timeoutSec = 600) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/omr/submit', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: { wait, timeout_sec: timeoutSec },
  });
  return response.data;
}

export async function getJobStatus(jobId) {
  const response = await api.get(`/omr/jobs/${jobId}`);
  return response.data;
}

export async function downloadXml(jobId) {
  const response = await api.get(`/omr/download/xml/${jobId}`, {
    responseType: 'blob',
  });
  return response;
}

export async function downloadMidi(jobId) {
  const response = await api.get(`/omr/download/midi/${jobId}`, {
    responseType: 'blob',
  });
  return response;
}
