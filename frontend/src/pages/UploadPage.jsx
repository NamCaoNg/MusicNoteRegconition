import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CircleCheck, CircleX, Download, File, Play, Upload } from 'lucide-react';
import { submitOMR, getJobStatus, downloadXml, downloadMidi } from '../services/omrService';
import { getApiErrorMessage } from '../utils/apiError';

const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'];
const MAX_SIZE_MB = 20;

export default function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const pollingRef = useRef(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const validateFile = useCallback((f) => {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large. Maximum size is ${MAX_SIZE_MB} MB.`;
    }
    return null;
  }, []);

  const handleFile = useCallback((f) => {
    setError('');
    setJob(null);
    const err = validateFile(f);
    if (err) {
      setError(err);
      return;
    }
    setFile(f);
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target.result);
    reader.readAsDataURL(f);
  }, [validateFile]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, [handleFile]);

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const pollJob = (jobId) => {
    pollingRef.current = setInterval(async () => {
      try {
        const data = await getJobStatus(jobId);
        setJob(data);
        if (data.status === 'completed') {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
          navigate(`/result/${data.job_id || jobId}`);
          return;
        }
        if (data.status === 'failed') {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      } catch (err) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
        const message = getApiErrorMessage(err, 'Failed to check status.');
        setJob((prev) => ({ ...prev, status: 'failed', error_message: message }));
      }
    }, 2000);
  };

  const handleSubmit = async () => {
    if (!file) return;
    setError('');
    setUploading(true);
    setJob(null);

    try {
      const data = await submitOMR(file, false);
      setJob(data);
      if (data.status === 'completed') {
        navigate(`/result/${data.job_id}`);
      } else if (data.status === 'processing') {
        pollJob(data.job_id);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Upload failed. Please try again.'));
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (type) => {
    if (!job) return;
    try {
      const response = type === 'xml'
        ? await downloadXml(job.job_id)
        : await downloadMidi(job.job_id);

      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${job.display_name}.${type === 'xml' ? 'xml' : 'mid'}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      setError(`Failed to download ${type.toUpperCase()} file.`);
    }
  };

  const resetUpload = () => {
    setFile(null);
    setPreview(null);
    setJob(null);
    setError('');
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Upload Score</h1>
        <p>Upload a music score image to recognize and convert to MusicXML & MIDI</p>
      </div>

      <div className="upload-section">
        {!file ? (
          <div
            className={`dropzone ${dragActive ? 'dropzone-active' : ''}`}
            onDrop={handleDrop}
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_EXTENSIONS.join(',')}
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              hidden
            />
            <Upload className="dropzone-icon" strokeWidth={1.5} />
            <p className="dropzone-text">Drag & drop your score image here</p>
            <p className="dropzone-hint">or click to browse - JPG, PNG, BMP, TIFF, WebP - Max {MAX_SIZE_MB}MB</p>
          </div>
        ) : (
          <div className="upload-preview">
            <div className="preview-image-container">
              <img src={preview} alt="Score preview" className="preview-image" />
            </div>
            <div className="preview-info">
              <div className="preview-filename">
                <File className="info-icon" />
                {file.name}
                <span className="file-size">({(file.size / 1024 / 1024).toFixed(2)} MB)</span>
              </div>
              <div className="preview-actions">
                {!job && (
                  <>
                    <button className="btn btn-primary" onClick={handleSubmit} disabled={uploading}>
                      {uploading ? (
                        <span className="btn-loading">
                          <span className="spinner" />
                          Submitting...
                        </span>
                      ) : (
                        <>
                          <Play className="btn-icon" />
                          Start
                        </>
                      )}
                    </button>
                    <button className="btn btn-outline" onClick={resetUpload}>Change File</button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="alert alert-error" style={{ marginTop: '16px' }}>
            <CircleX className="alert-icon" />
            {error}
          </div>
        )}

        {job && (
          <div className="job-status-card">
            <div className="job-status-header">
              <span className="job-id">{job.job_id}</span>
            </div>

            {job.status === 'processing' && (
              <div className="processing-info">
                <div className="progress-bar-container">
                  <div className="progress-bar-indeterminate" />
                </div>
                <p>Processing your score... This may take a few minutes.</p>
              </div>
            )}

            {job.status === 'completed' && (
              <div className="completed-info">
                <CircleCheck className="completed-icon" />
                <p>Processing complete! Download your files below.</p>
                <div className="download-buttons">
                  <button className="btn btn-primary" onClick={() => handleDownload('xml')}>
                    <Download className="btn-icon" />
                    Download MusicXML
                  </button>
                  <button className="btn btn-secondary" onClick={() => handleDownload('midi')}>
                    <Download className="btn-icon" />
                    Download MIDI
                  </button>
                </div>
                <button className="btn btn-outline" onClick={resetUpload} style={{ marginTop: '12px' }}>
                  Upload Another Score
                </button>
              </div>
            )}

            {job.status === 'failed' && (
              <div className="failed-info">
                <CircleX className="failed-icon" />
                <p>{job.error_message || 'Processing failed.'}</p>
                <button className="btn btn-outline" onClick={resetUpload}>Try Again</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
