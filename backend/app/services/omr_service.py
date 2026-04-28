import os
import threading
import traceback

from app.db import SessionLocal
from app.models import Job
from app.services.job_service import update_job_completed, update_job_failed
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_CONCURRENT_OMR_JOBS = int(os.getenv("MAX_CONCURRENT_OMR_JOBS", "2"))
_JOB_SEMAPHORE = threading.BoundedSemaphore(value=max(1, MAX_CONCURRENT_OMR_JOBS))


def process_score_image(input_path: str, output_dir: str) -> dict:
    """Run the OMR pipeline on an image. Returns paths to output files."""
    from src.main import run_pipeline

    os.makedirs(output_dir, exist_ok=True)

    result = run_pipeline(img_path=input_path, output_dir=output_dir)

    xml_path = result.get("xml_path")
    midi_path = result.get("midi_path")

    if not xml_path or not os.path.exists(xml_path):
        raise FileNotFoundError(f"Pipeline finished but XML file was not created: {xml_path}")

    if not midi_path or not os.path.exists(midi_path):
        raise FileNotFoundError(f"Pipeline finished but MIDI file was not created: {midi_path}")

    return {
        "output_dir": result.get("output_folder", output_dir),
        "xml_path": xml_path,
        "midi_path": midi_path,
    }


def run_omr_background(job_id: str, input_path: str, output_dir: str) -> bool:
    """
    Run OMR pipeline in a background thread.
    On success: update job status to 'completed'.
    On failure: mark as 'failed'.
    """

    acquired = _JOB_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        logger.warning(f"[{job_id}] OMR worker pool is full")
        return False

    def _worker():
        db = SessionLocal()
        try:
            logger.info(f"[{job_id}] Background OMR started")
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job is None:
                logger.warning(f"[{job_id}] Job not found in database")
                return

            try:
                result = process_score_image(input_path=input_path, output_dir=output_dir)
                update_job_completed(
                    db=db,
                    job=job,
                    output_dir=result["output_dir"],
                    xml_path=result["xml_path"],
                    midi_path=result["midi_path"],
                )
                logger.info(f"[{job_id}] Background OMR completed successfully")
            except Exception:
                logger.exception(f"[{job_id}] Background OMR failed")
                error_message = "OMR processing failed"
                # Keep the error concise for API responses while preserving useful context.
                # Thread workers should not leak huge tracebacks into DB payloads.
                try:
                    last_exc = traceback.format_exc().strip().splitlines()
                    if last_exc:
                        error_message = last_exc[-1][:500]
                except Exception:
                    error_message = "OMR processing failed"
                update_job_failed(db, job, error_message=error_message)
        finally:
            db.close()
            _JOB_SEMAPHORE.release()

    thread = threading.Thread(target=_worker, daemon=True, name=f"omr-{job_id}")
    thread.start()
    return True