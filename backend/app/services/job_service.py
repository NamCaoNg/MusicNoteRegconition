import os
import shutil
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Job

PROCESSING_STALE_MINUTES = int(os.getenv("PROCESSING_STALE_MINUTES", "30"))


def _now_utc():
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_job(
    db: Session,
    job_id: str,
    user_id: int,
    display_name: str,
    filename: str,
    input_path: str) -> Job:
    job = Job(
        job_id=job_id,
        user_id=user_id,
        display_name=display_name,
        filename=filename,
        input_path=input_path,
        status="processing",
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job_by_job_id(db: Session, job_id: str) -> Job | None:
    return db.query(Job).filter(Job.job_id == job_id).first()


def mark_job_failed_if_stale(db: Session, job: Job) -> Job:
    if job.status != "processing":
        return job

    last_update = _as_utc(job.updated_at or job.created_at)
    stale_after = timedelta(minutes=max(1, PROCESSING_STALE_MINUTES))
    if _now_utc() - last_update <= stale_after:
        return job

    return update_job_failed(
        db,
        job,
        "Processing timed out. The backend may have restarted while this job was running.",
    )


def mark_stale_processing_jobs_failed(db: Session, user_id: int | None = None) -> int:
    query = db.query(Job).filter(Job.status == "processing")
    if user_id is not None:
        query = query.filter(Job.user_id == user_id)

    count = 0
    for job in query.all():
        original_status = job.status
        mark_job_failed_if_stale(db, job)
        if original_status != job.status:
            count += 1
    return count


def mark_processing_jobs_failed_after_restart(db: Session) -> int:
    count = 0
    for job in db.query(Job).filter(Job.status == "processing").all():
        update_job_failed(
            db,
            job,
            "Processing was interrupted because the backend restarted.",
        )
        count += 1
    return count


def _base_user_jobs_query(db: Session, user_id: int):
    return db.query(Job).filter(
        Job.user_id == user_id,
        Job.status.in_(["completed", "processing"]),
    )


def get_user_jobs(db: Session, user_id: int, offset: int = 0, limit: int = 5) -> list[Job]:
    return (
        _base_user_jobs_query(db, user_id)
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_user_jobs(db: Session, user_id: int) -> int:
    return _base_user_jobs_query(db, user_id).count()


def _base_search_user_jobs_query(db: Session, user_id: int, keyword: str):
    return (
        _base_user_jobs_query(db, user_id)
        .filter(
            or_(
                Job.display_name.ilike(f"%{keyword}%"),
                Job.job_id.ilike(f"%{keyword}%"),
            ),
        )
    )


def search_user_jobs(db: Session, user_id: int, keyword: str, offset: int = 0, limit: int = 5) -> list[Job]:
    return (
        _base_search_user_jobs_query(db, user_id, keyword)
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_search_user_jobs(db: Session, user_id: int, keyword: str) -> int:
    return _base_search_user_jobs_query(db, user_id, keyword).count()


def get_user_jobs_by_display_name(db: Session, user_id: int, display_name: str) -> list[Job]:
    return (
        db.query(Job)
        .filter(
            Job.user_id == user_id,
            Job.display_name == display_name,
        )
        .order_by(Job.created_at.desc())
        .all()
    )


def rename_job(db: Session, job: Job, new_name: str) -> Job:
    job.display_name = new_name
    job.updated_at = _now_utc()
    db.commit()
    db.refresh(job)
    return job


def _delete_input_file(job: Job) -> None:
    if job.input_path and os.path.isfile(job.input_path):
        try:
            os.remove(job.input_path)
        except OSError:
            pass


def update_job_completed(
    db: Session,
    job: Job,
    output_dir: str,
    xml_path: str | None,
    midi_path: str | None) -> Job:
    job.status = "completed"
    job.output_dir = output_dir
    job.xml_path = xml_path
    job.midi_path = midi_path
    job.error_message = None
    job.updated_at = _now_utc()
    _delete_input_file(job)
    db.commit()
    db.refresh(job)
    return job


def update_job_failed(db: Session, job: Job, error_message: str) -> Job:
    job.status = "failed"
    job.error_message = error_message
    job.updated_at = _now_utc()
    _delete_input_file(job)
    db.commit()
    db.refresh(job)
    return job


def delete_job(db: Session, job: Job) -> None:
    if job.output_dir and os.path.isdir(job.output_dir):
        shutil.rmtree(job.output_dir, ignore_errors=True)

    _delete_input_file(job)

    db.delete(job)
    db.commit()
