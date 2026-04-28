from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.deps import get_db
from app.error_utils import build_error_detail
from app.models import User
from app.schemas import JobResponse, JobRename, JobListResponse, JobResultRawResponse
from app.api.routes.omr_routes import get_job_result_raw
from app.services.job_service import (
    get_user_jobs,
    count_user_jobs,
    search_user_jobs,
    count_search_user_jobs,
    get_job_by_job_id,
    get_user_jobs_by_display_name,
    mark_job_failed_if_stale,
    mark_stale_processing_jobs_failed,
    rename_job,
    delete_job,
)

router = APIRouter()


@router.get("", response_model=JobListResponse)
def list_history(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(5, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get paginated results in history (only completed and processing jobs)."""
    mark_stale_processing_jobs_failed(db, user_id=current_user.id)
    total = count_user_jobs(db, user_id=current_user.id)
    total_pages = max(1, (total + limit - 1) // limit)
    normalized_page = min(page, total_pages)
    offset = (normalized_page - 1) * limit
    jobs = get_user_jobs(db, user_id=current_user.id, offset=offset, limit=limit)
    return JobListResponse(jobs=jobs, total=total, page=normalized_page, limit=limit, total_pages=total_pages)


@router.get("/search", response_model=JobListResponse)
def search_history(
    q: str = Query(..., min_length=1, description="Search keyword for display name"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(5, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search paginated results by display name or job ID."""
    mark_stale_processing_jobs_failed(db, user_id=current_user.id)
    total = count_search_user_jobs(db, user_id=current_user.id, keyword=q)
    total_pages = max(1, (total + limit - 1) // limit)
    normalized_page = min(page, total_pages)
    offset = (normalized_page - 1) * limit
    jobs = search_user_jobs(db, user_id=current_user.id, keyword=q, offset=offset, limit=limit)
    return JobListResponse(jobs=jobs, total=total, page=normalized_page, limit=limit, total_pages=total_pages)


@router.get("/{identifier}", response_model=JobResponse)
def get_history_detail(
    identifier: str = Path(..., description="job_id or exact display_name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details by job_id or exact display_name."""
    job = get_job_by_job_id(db, identifier)

    if not job:
        matched_jobs = get_user_jobs_by_display_name(db, current_user.id, identifier)
        if len(matched_jobs) == 0:
            raise HTTPException(
                status_code=404,
                detail=build_error_detail("history_result_not_found", "Result not found"),
            )
        if len(matched_jobs) > 1:
            raise HTTPException(
                status_code=409,
                detail=build_error_detail(
                    "history_display_name_ambiguous",
                    "Multiple results share this display_name. Please query by job_id.",
                ),
            )
        job = matched_jobs[0]

    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("history_result_not_found", "Result not found"),
        )

    job = mark_job_failed_if_stale(db, job)

    if job.status == "failed":
        error_msg = job.error_message or "Unknown error"
        delete_job(db, job)
        raise HTTPException(
            status_code=422,
            detail=build_error_detail(
                "history_processing_failed",
                f"Processing failed: {error_msg}. Result has been automatically removed.",
            ),
        )

    return job


@router.get("/{job_id}/result/raw", response_model=JobResultRawResponse)
def get_history_result_raw(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get display-ready result content from history context (images/XML/MIDI)."""
    return get_job_result_raw(job_id=job_id, db=db, current_user=current_user)


@router.put("/{job_id}/rename", response_model=JobResponse)
def rename_result(
    job_id: str,
    payload: JobRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename a result (max 50 chars, no special characters)."""
    job = get_job_by_job_id(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("history_result_not_found", "Result not found"),
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("history_rename_only_completed", "Can only rename completed results"),
        )

    job = rename_job(db, job, new_name=payload.new_name)
    return job


@router.delete("", status_code=204)
def delete_result_by_identifier(
    job_id: str | None = Query(None, description="Job ID to delete"),
    display_name: str | None = Query(None, description="Display name to delete"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a result by job_id or display_name."""
    if not job_id and not display_name:
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("history_missing_identifier", "Provide either job_id or display_name"),
        )

    if job_id:
        job = get_job_by_job_id(db, job_id)
        if not job or job.user_id != current_user.id:
            raise HTTPException(
                status_code=404,
                detail=build_error_detail("history_result_not_found", "Result not found"),
            )

        if display_name and job.display_name != display_name:
            raise HTTPException(
                status_code=400,
                detail=build_error_detail(
                    "history_identifier_mismatch",
                    "display_name does not match the given job_id",
                ),
            )

        delete_job(db, job)
        return None

    matched_jobs = get_user_jobs_by_display_name(db, current_user.id, display_name)
    if len(matched_jobs) == 0:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("history_result_not_found", "Result not found"),
        )
    if len(matched_jobs) > 1:
        raise HTTPException(
            status_code=409,
            detail=build_error_detail(
                "history_display_name_ambiguous",
                "Multiple results share this display_name. Please delete by job_id.",
            ),
        )

    delete_job(db, matched_jobs[0])
    return None
