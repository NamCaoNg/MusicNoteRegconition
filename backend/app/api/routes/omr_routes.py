import os
import re
import time
import base64
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.deps import get_db
from app.error_utils import build_error_detail
from app.models import Job, User
from app.schemas import JobResponse, JobResultResponse, JobResultRawResponse
from app.services.job_service import create_job, get_job_by_job_id, mark_job_failed_if_stale, delete_job
from app.services.omr_service import run_omr_background
from src.core.config import OUTPUTS_DIR, UPLOADS_DIR

router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _generate_job_id() -> str:
    """Generate short, readable, low-collision job_id."""
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_suffix = uuid.uuid4().hex[:6]
    return f"score_{now}_{short_suffix}"


def _sanitize_filename(filename: str) -> str:
    """Normalize user-supplied filename to a safe basename."""
    base_name = os.path.basename(filename).strip()
    if not base_name:
        return "unknown.png"

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", base_name)
    safe_name = safe_name.lstrip(".")
    return safe_name or "unknown.png"


def _wait_for_terminal_status(
    db: Session,
    job_id: str,
    timeout_sec: int,
    poll_interval_sec: float = 0.25,
) -> Job | None:
    """Wait until a job becomes completed/failed, or timeout."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        # Force the session to fetch latest row state updated by background worker.
        db.expire_all()
        job = get_job_by_job_id(db, job_id)
        if job is None:
            return None
        if job.status in {"completed", "failed"}:
            return job
        time.sleep(poll_interval_sec)

    db.expire_all()
    return get_job_by_job_id(db, job_id)


def _save_upload_with_limits(file: UploadFile, input_path: str) -> None:
    total_written = 0
    chunk_size = 1024 * 1024

    with open(input_path, "wb") as buffer:
        while True:
            chunk = file.file.read(chunk_size)
            if not chunk:
                break
            total_written += len(chunk)
            if total_written > MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=build_error_detail(
                        "omr_upload_too_large",
                        f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB",
                    ),
                )
            buffer.write(chunk)


def _validate_saved_image(input_path: str) -> None:
    try:
        with Image.open(input_path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("omr_invalid_image", "Uploaded file is not a valid image"),
        )


def _to_output_static_url(job_id: str, file_path: str | None) -> str | None:
    if not file_path:
        return None
    filename = os.path.basename(file_path)
    if not filename:
        return None
    return f"/outputs/{job_id}/{filename}"


def _read_xml_content(xml_path: str) -> str:
    with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _read_file_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _detect_image_mime(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".bmp":
        return "image/bmp"
    return "image/png"


def _build_job_result_response(job: Job) -> JobResultResponse:
    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("omr_job_not_completed", "Job is not completed yet"),
        )

    if not job.xml_path or not os.path.exists(job.xml_path):
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_xml_not_found", "XML file not found"),
        )

    if not job.midi_path or not os.path.exists(job.midi_path):
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_midi_not_found", "MIDI file not found"),
        )

    return JobResultResponse(
        job_id=job.job_id,
        status=job.status,
        teaser_image_url=job.teaser_image_url,
        pitch_image_url=job.pitch_image_url,
        xml_download_url=job.xml_download_url,
        midi_download_url=job.midi_download_url,
        xml_file_url=_to_output_static_url(job.job_id, job.xml_path),
        midi_file_url=_to_output_static_url(job.job_id, job.midi_path),
        xml_content=_read_xml_content(job.xml_path),
    )


def _build_job_result_raw_response(job: Job) -> JobResultRawResponse:
    _ = _build_job_result_response(job)

    teaser_path: str | None = None
    pitch_path: str | None = None
    if job.output_dir and job.xml_path:
        xml_stem = os.path.splitext(os.path.basename(job.xml_path))[0]
        teaser_candidate = os.path.join(job.output_dir, f"{xml_stem}_teaser.png")
        pitch_candidate = os.path.join(job.output_dir, f"{xml_stem}_pitch.png")
        if os.path.exists(teaser_candidate):
            teaser_path = teaser_candidate
        if os.path.exists(pitch_candidate):
            pitch_path = pitch_candidate

    teaser_base64: str | None = None
    teaser_mime: str | None = None
    if teaser_path:
        teaser_base64 = _read_file_base64(teaser_path)
        teaser_mime = _detect_image_mime(teaser_path)

    pitch_base64: str | None = None
    pitch_mime: str | None = None
    if pitch_path:
        pitch_base64 = _read_file_base64(pitch_path)
        pitch_mime = _detect_image_mime(pitch_path)

    # midi_path/xml_path are guaranteed by _build_job_result_response validation above.
    assert job.xml_path is not None
    assert job.midi_path is not None

    return JobResultRawResponse(
        job_id=job.job_id,
        status=job.status,
        teaser_image_mime_type=teaser_mime,
        teaser_image_base64=teaser_base64,
        pitch_image_mime_type=pitch_mime,
        pitch_image_base64=pitch_base64,
        xml_content=_read_xml_content(job.xml_path),
        midi_mime_type="audio/midi",
        midi_base64=_read_file_base64(job.midi_path),
    )


@router.post("/submit", response_model=JobResponse | JobResultResponse)
def submit_omr(
    file: UploadFile = File(...),
    wait: bool = Query(False, description="Wait until processing completes"),
    timeout_sec: int = Query(600, ge=1, le=3600, description="Max wait time in seconds when wait=true"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a score image and start OMR processing in the background.
    Returns immediately with job status 'processing'.
    Poll GET /omr/jobs/{job_id} to check progress.
    """
    # Validate file extension
    filename = _sanitize_filename(file.filename or "unknown.png")
    _, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=build_error_detail(
                "omr_unsupported_file_type",
                f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            ),
        )

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    job_id = _generate_job_id()
    display_name = job_id

    input_path = str(UPLOADS_DIR / f"{job_id}_{filename}")
    job_output_dir = str(OUTPUTS_DIR / job_id)

    # Save and validate uploaded file
    try:
        _save_upload_with_limits(file, input_path)
    except HTTPException:
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except OSError:
                pass
        raise
    finally:
        file.file.close()

    try:
        _validate_saved_image(input_path)
    except HTTPException:
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except OSError:
                pass
        raise

    # Create job record
    job = create_job(
        db=db,
        job_id=job_id,
        user_id=current_user.id,
        display_name=display_name,
        filename=filename,
        input_path=input_path,
    )

    # Start background processing
    started = run_omr_background(
        job_id=job_id,
        input_path=input_path,
        output_dir=job_output_dir,
    )

    if not started:
        delete_job(db, job)
        raise HTTPException(
            status_code=429,
            detail=build_error_detail(
                "omr_worker_pool_busy",
                "System is busy. Too many processing jobs, please retry shortly.",
            ),
        )

    if wait:
        final_job = _wait_for_terminal_status(db, job_id, timeout_sec)
        if final_job is not None:
            if final_job.status == "failed":
                error_msg = final_job.error_message or "Unknown error"
                delete_job(db, final_job)
                raise HTTPException(
                    status_code=422,
                    detail=build_error_detail(
                        "omr_processing_failed",
                        f"Processing failed: {error_msg}. Job has been automatically removed from history.",
                    ),
                )
            if final_job.status == "completed":
                return _build_job_result_response(final_job)
            return final_job

    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the current status of a job.
    If the job has failed, return error message and auto-delete it.
    """
    job = get_job_by_job_id(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_job_not_found", "Job not found"),
        )

    job = mark_job_failed_if_stale(db, job)

    if job.status == "failed":
        error_msg = job.error_message or "Unknown error"
        delete_job(db, job)
        raise HTTPException(
            status_code=422,
            detail=build_error_detail(
                "omr_processing_failed",
                f"Processing failed: {error_msg}. Job has been automatically removed from history.",
            ),
        )

    return job


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
def get_job_result(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get rich result payload for a completed OMR job.
    Includes preview URLs, direct static file URLs, and XML text content.
    """
    job = get_job_by_job_id(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_job_not_found", "Job not found"),
        )

    job = mark_job_failed_if_stale(db, job)

    if job.status == "failed":
        error_msg = job.error_message or "Unknown error"
        delete_job(db, job)
        raise HTTPException(
            status_code=422,
            detail=build_error_detail(
                "omr_processing_failed",
                f"Processing failed: {error_msg}. Job has been automatically removed from history.",
            ),
        )

    return _build_job_result_response(job)


@router.get("/jobs/{job_id}/result/raw", response_model=JobResultRawResponse)
def get_job_result_raw(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get direct result content in one payload.
    - XML as plain text
    - MIDI as base64
    - teaser/pitch image as base64 when available
    """
    job = get_job_by_job_id(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_job_not_found", "Job not found"),
        )

    job = mark_job_failed_if_stale(db, job)

    if job.status == "failed":
        error_msg = job.error_message or "Unknown error"
        delete_job(db, job)
        raise HTTPException(
            status_code=422,
            detail=build_error_detail(
                "omr_processing_failed",
                f"Processing failed: {error_msg}. Job has been automatically removed from history.",
            ),
        )

    return _build_job_result_raw_response(job)


@router.get("/download/xml/{job_id}")
def download_xml(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the MusicXML output file."""
    job = get_job_by_job_id(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_job_not_found", "Job not found"),
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("omr_job_not_completed", "Job is not completed yet"),
        )

    if not job.xml_path or not os.path.exists(job.xml_path):
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_xml_not_found", "XML file not found"),
        )

    download_name = f"{job.display_name}.xml"
    return FileResponse(job.xml_path, filename=download_name, media_type="application/xml")


@router.get("/download/midi/{job_id}")
def download_midi(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the MIDI output file."""
    job = get_job_by_job_id(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_job_not_found", "Job not found"),
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("omr_job_not_completed", "Job is not completed yet"),
        )

    if not job.midi_path or not os.path.exists(job.midi_path):
        raise HTTPException(
            status_code=404,
            detail=build_error_detail("omr_midi_not_found", "MIDI file not found"),
        )

    download_name = f"{job.display_name}.mid"
    return FileResponse(job.midi_path, filename=download_name, media_type="audio/midi")
