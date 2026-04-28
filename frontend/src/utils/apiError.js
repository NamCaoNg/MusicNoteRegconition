export function getApiErrorMessage(err, fallback = 'Request failed.') {
    const data = err?.response?.data;

    // New backend error format: { success: false, error: { code, message, details } }
    const structuredMessage = data?.error?.message;
    if (typeof structuredMessage === 'string' && structuredMessage.trim()) {
        return structuredMessage;
    }

    // Legacy format support: { detail: string | { message: string } }
    const detail = data?.detail;
    if (typeof detail === 'object' && typeof detail?.message === 'string' && detail.message.trim()) {
        return detail.message;
    }
    if (typeof detail === 'string' && detail.trim()) {
        return detail;
    }

    // Generic error field fallback.
    if (typeof data?.message === 'string' && data.message.trim()) {
        return data.message;
    }

    return fallback;
}
