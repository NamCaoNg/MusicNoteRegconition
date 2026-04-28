import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { CircleX, Clock, File, Search, X } from 'lucide-react';
import { listHistory, searchHistory, renameJob, deleteJob } from '../services/historyService';
import { getApiErrorMessage } from '../utils/apiError';

const JOBS_PER_PAGE = 5;

export default function HistoryPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState('1');

  // Thêm tham số silent để phân biệt lần đầu load và poll ngầm
  const fetchJobs = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const data = searchQuery.trim()
        ? await searchHistory(searchQuery.trim(), { page: currentPage, limit: JOBS_PER_PAGE })
        : await listHistory({ page: currentPage, limit: JOBS_PER_PAGE });
      setJobs(data.jobs);
      setTotal(data.total);
      setTotalPages(data.total_pages ?? 1);
      if (data.page && data.page !== currentPage) {
        setCurrentPage(data.page);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load history.'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [searchQuery, currentPage]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  // Polling: chỉ chạy khi có job đang processing, tự dừng khi hết
  const hasProcessingJobs = jobs.some((j) => j.status === 'processing');
  useEffect(() => {
    if (!hasProcessingJobs) return;
    const interval = setInterval(() => fetchJobs(true), 10000);
    return () => clearInterval(interval);
  }, [hasProcessingJobs, fetchJobs]);

  const handleSearch = (e) => {
    e.preventDefault();
    if (currentPage !== 1) {
      setCurrentPage(1);
      return;
    }
    fetchJobs();
  };

  const handleRename = async (jobId) => {
    if (!editName.trim()) return;
    try {
      const updated = await renameJob(jobId, editName.trim());
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? updated : j)));
      setEditingId(null);
      setEditName('');
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to rename.'));
    }
  };

  const handleDelete = async (jobId) => {
    if (!window.confirm('Are you sure you want to delete this result?')) return;
    try {
      await deleteJob({ jobId });
      await fetchJobs(true);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to delete.'));
    }
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

  const openResult = (jobId) => {
    if (editingId === jobId) return;
    navigate(`/result/${jobId}`);
  };

  const handleJumpToPage = (e) => {
    e.preventDefault();
    const parsedPage = Number.parseInt(pageInput, 10);
    if (Number.isNaN(parsedPage)) {
      setPageInput(String(currentPage));
      return;
    }

    const normalizedPage = Math.min(totalPages, Math.max(1, parsedPage));
    setCurrentPage(normalizedPage);
    setPageInput(String(normalizedPage));
  };

  const visibleStart = total === 0 ? 0 : (currentPage - 1) * JOBS_PER_PAGE + 1;
  const visibleEnd = total === 0 ? 0 : Math.min(currentPage * JOBS_PER_PAGE, total);

  return (
    <div className="page-content">
      <form className="search-bar" onSubmit={handleSearch}>
        <Search className="search-icon" />
        <input
          type="text"
          placeholder="Search by name"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setCurrentPage(1);
          }}
          className="search-input"
        />
        {searchQuery && (
          <button
            type="button"
            className="search-clear"
            aria-label="Clear search"
            onClick={() => {
              setSearchQuery('');
              setCurrentPage(1);
            }}
          >
            <X aria-hidden="true" />
          </button>
        )}
      </form>

      {error && (
        <div className="alert alert-error">
          <CircleX className="alert-icon" />
          {error}
          <button className="alert-dismiss" aria-label="Dismiss error" onClick={() => setError('')}>
            <X aria-hidden="true" />
          </button>
        </div>
      )}

      {loading ? (
        <div className="loading-state">
          <span className="spinner spinner-lg" />
          <p>Loading history...</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <File className="empty-icon" strokeWidth={1.5} />
          <h3>No results yet</h3>
          <p>{searchQuery ? 'No results match your search.' : 'Upload a score to get started!'}</p>
        </div>
      ) : (
        <>
          <p className="results-count">
            Showing {visibleStart}-{visibleEnd} of {total} result{total !== 1 ? 's' : ''}
          </p>
          <div className="history-list">
            {jobs.map((job) => (
              <div
                key={job.job_id}
                className={`history-card ${editingId === job.job_id ? '' : 'history-card-clickable'}`}
                onClick={() => openResult(job.job_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openResult(job.job_id);
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={`Open result ${job.display_name}`}
              >
                <div className="history-card-header">
                  <div className="history-card-title">
                    {editingId === job.job_id ? (
                      <div className="inline-edit">
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            e.stopPropagation();
                            if (e.key === 'Enter') handleRename(job.job_id);
                            if (e.key === 'Escape') { setEditingId(null); setEditName(''); }
                          }}
                          autoFocus
                          className="inline-edit-input"
                        />
                        <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); handleRename(job.job_id); }}>Save</button>
                        <button className="btn btn-sm btn-outline" onClick={(e) => { e.stopPropagation(); setEditingId(null); setEditName(''); }}>Cancel</button>
                      </div>
                    ) : (
                      <h3>{job.display_name}</h3>
                    )}
                  </div>
                  <div className="history-card-meta">
                    <span className="meta-item">
                      <File className="meta-icon" />
                      {job.filename}
                    </span>
                  </div>
                </div>

                <div className="history-card-actions" onClick={(e) => e.stopPropagation()}>
                  {job.status === 'completed' && (
                    <span className="meta-item">
                      <Clock className="meta-icon" />
                      {formatDate(job.created_at)}
                    </span>
                  )}
                  {job.status === 'completed' && (
                    <>
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={() => { setEditingId(job.job_id); setEditName(job.display_name); }}
                      >
                        Rename
                      </button>
                    </>
                  )}
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={() => handleDelete(job.job_id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="history-pagination" role="navigation" aria-label="History pagination">
            <button
              className="btn btn-sm btn-outline"
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
            >
              First
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
            >
              Prev
            </button>
            <span className="history-pagination-info">
              Page {currentPage} / {totalPages}
            </span>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
            >
              Next
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
            >
              Last
            </button>
            <form className="history-pagination-jump" onSubmit={handleJumpToPage}>
              <input
                id="history-page-input"
                type="number"
                min="1"
                max={totalPages}
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                className="history-pagination-input"
                aria-label="Jump to page"
              />
              <button className="btn btn-sm btn-outline" type="submit">Go</button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
