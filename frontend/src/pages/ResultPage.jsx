import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CircleX } from 'lucide-react';

import { getHistoryDetail } from '../services/historyService';
import { downloadMidi, downloadXml } from '../services/omrService';
import { getApiErrorMessage } from '../utils/apiError';
import { API_BASE_URL } from '../api/axios';

const IMAGE_KEY_HINTS = ['image', 'img', 'preview', 'thumbnail', 'annotated', 'output', 'input'];
const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'];
const NON_IMAGE_KEYS = ['filename'];

function joinApiUrl(path) {
    const base = API_BASE_URL.replace(/\/+$/, '');
    const suffix = path.replace(/^\/+/, '');
    return `${base}/${suffix}`;
}

function isLikelyImageUrl(value) {
    if (typeof value !== 'string') return false;
    const lower = value.toLowerCase().trim();

    if (lower.startsWith('data:image/')) return true;
    if (/^https?:\/\//i.test(lower)) {
        return IMAGE_EXTENSIONS.some((ext) => lower.includes(ext));
    }
    if (lower.startsWith('/')) {
        return IMAGE_EXTENSIONS.some((ext) => lower.includes(ext));
    }
    if (lower.startsWith('outputs/')) {
        return IMAGE_EXTENSIONS.some((ext) => lower.includes(ext));
    }

    return false;
}

function normalizeAssetUrl(value) {
    if (typeof value !== 'string') return value;
    if (/^https?:\/\//i.test(value) || value.startsWith('data:image/')) {
        return value;
    }
    if (value.startsWith('/api/')) {
        return value;
    }
    if (value.startsWith('/')) {
        return joinApiUrl(value);
    }
    return joinApiUrl(value);
}

function collectImageCandidates(payload) {
    const results = [];
    const seen = new Set();

    const walk = (node, path = '', depth = 0) => {
        if (node == null || depth > 6) return;

        if (typeof node === 'string') {
            if (isLikelyImageUrl(node)) {
                const src = normalizeAssetUrl(node);
                if (!seen.has(src)) {
                    seen.add(src);
                    results.push({
                        label: path || 'Image',
                        src,
                    });
                }
            }
            return;
        }

        if (Array.isArray(node)) {
            node.forEach((item, index) => {
                walk(item, `${path}[${index}]`, depth + 1);
            });
            return;
        }

        if (typeof node === 'object') {
            Object.entries(node).forEach(([key, value]) => {
                const nextPath = path ? `${path}.${key}` : key;
                const lowerKey = key.toLowerCase();

                if (
                    typeof value === 'string' &&
                    IMAGE_KEY_HINTS.some((hint) => lowerKey.includes(hint)) &&
                    !NON_IMAGE_KEYS.includes(lowerKey) &&
                    isLikelyImageUrl(value)
                ) {
                    const src = normalizeAssetUrl(value);
                    if (!seen.has(src)) {
                        seen.add(src);
                        results.push({ label: nextPath, src });
                    }
                }

                if (!NON_IMAGE_KEYS.includes(lowerKey)) {
                    walk(value, nextPath, depth + 1);
                }
            });
        }
    };

    walk(payload);
    return results;
}

export default function ResultPage() {
    const { identifier } = useParams();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [job, setJob] = useState(null);
    const [activeTab, setActiveTab] = useState('teaser');

    const fetchDetail = useCallback(async ({ showLoading = false } = {}) => {
        if (showLoading) {
            setLoading(true);
        }
        setError('');
        try {
            const data = await getHistoryDetail(identifier);
            setJob(data);
        } catch (err) {
            setError(getApiErrorMessage(err, 'Failed to load result details.'));
        } finally {
            if (showLoading) {
                setLoading(false);
            }
        }
    }, [identifier]);

    useEffect(() => {
        fetchDetail({ showLoading: true });
    }, [fetchDetail]);

    useEffect(() => {
        if (job?.status !== 'processing') return;

        const interval = setInterval(() => {
            fetchDetail();
        }, 5000);

        return () => clearInterval(interval);
    }, [job?.status, fetchDetail]);

    const createdAtText = useMemo(() => {
        if (!job?.created_at) return '-';
        const date = new Date(job.created_at);
        return Number.isNaN(date.getTime()) ? job.created_at : date.toLocaleString();
    }, [job]);

    const imageCandidates = useMemo(() => collectImageCandidates(job), [job]);

    const teaserImage = useMemo(
        () => imageCandidates.find((item) => item.label.toLowerCase().includes('teaser')),
        [imageCandidates]
    );

    const pitchImage = useMemo(
        () => imageCandidates.find((item) => item.label.toLowerCase().includes('pitch')),
        [imageCandidates]
    );

    useEffect(() => {
        if (teaserImage) {
            setActiveTab('teaser');
        } else if (pitchImage) {
            setActiveTab('pitch');
        }
    }, [teaserImage, pitchImage]);

    const handleDownload = async (type) => {
        const jobId = job?.job_id || identifier;
        if (!jobId) return;

        try {
            const response = type === 'xml'
                ? await downloadXml(jobId)
                : await downloadMidi(jobId);
            const blob = new Blob([response.data]);
            const url = window.URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = `${job?.display_name || 'result'}.${type === 'xml' ? 'xml' : 'mid'}`;
            document.body.appendChild(anchor);
            anchor.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(anchor);
        } catch {
            setError(`Failed to download ${type.toUpperCase()} file.`);
        }
    };

    return (
        <div className="page-content">
            <div className="page-header">
                <div className="page-header-top">
                    <h1>{job?.display_name || 'Result Details'}</h1>
                    {!loading && !error && job?.status === 'completed' && (
                        <span className="result-header-created" title="Created time">
                            {createdAtText}
                        </span>
                    )}
                </div>
                <p>{job?.filename || 'Loading file name...'}</p>
            </div>

            {loading ? (
                <div className="loading-state">
                    <span className="spinner spinner-lg" />
                    <p>Loading result...</p>
                </div>
            ) : error ? (
                <div className="alert alert-error">
                    <CircleX className="alert-icon" />
                    {error}
                </div>
            ) : (
                <div className="result-card">
                    <div className="result-images-section">
                        {job?.status === 'processing' ? (
                            <div className="job-status-card">
                                <div className="job-status-header">
                                    <span className="job-id">{job.job_id || identifier}</span>
                                </div>
                                <div className="processing-info">
                                    <div className="progress-bar-container">
                                        <div className="progress-bar-indeterminate" />
                                    </div>
                                    <p>Processing your score... This may take a few minutes.</p>
                                </div>
                            </div>
                        ) : teaserImage || pitchImage ? (
                            <>
                                <div className="result-toolbar">
                                    <div className="result-tabs">
                                        {teaserImage && (
                                            <button
                                                type="button"
                                                className={`btn ${activeTab === 'teaser' ? 'btn-primary' : 'btn-outline'}`}
                                                onClick={() => setActiveTab('teaser')}
                                            >
                                                Teaser
                                            </button>
                                        )}
                                        {pitchImage && (
                                            <button
                                                type="button"
                                                className={`btn ${activeTab === 'pitch' ? 'btn-primary' : 'btn-outline'}`}
                                                onClick={() => setActiveTab('pitch')}
                                            >
                                                Pitch
                                            </button>
                                        )}
                                    </div>

                                    <div className="result-actions result-actions-top">
                                        <button
                                            className="btn btn-primary"
                                            onClick={() => handleDownload('xml')}
                                            disabled={job?.status !== 'completed'}
                                        >
                                            Download MusicXML
                                        </button>
                                        <button
                                            className="btn btn-secondary"
                                            onClick={() => handleDownload('midi')}
                                            disabled={job?.status !== 'completed'}
                                        >
                                            Download MIDI
                                        </button>
                                    </div>
                                </div>

                                <div className="result-images-grid">
                                    {activeTab === 'teaser' && teaserImage && (
                                        <figure className="result-image-card">
                                            <img
                                                src={teaserImage.src}
                                                alt="Teaser"
                                                className="result-image"
                                                loading="lazy"
                                            />
                                        </figure>
                                    )}

                                    {activeTab === 'pitch' && pitchImage && (
                                        <figure className="result-image-card">
                                            <img
                                                src={pitchImage.src}
                                                alt="Pitch"
                                                className="result-image"
                                                loading="lazy"
                                            />
                                        </figure>
                                    )}
                                </div>
                            </>
                        ) : (
                            <p className="result-no-image">
                                No images available yet!!!
                            </p>
                        )}
                    </div>

                    {job?.error_message && (
                        <div className="alert alert-error" style={{ marginTop: '16px' }}>
                            <CircleX className="alert-icon" />
                            {job.error_message}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
