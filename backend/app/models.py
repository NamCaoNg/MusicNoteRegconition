from pathlib import Path

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    jobs = relationship("Job", back_populates="owner")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    display_name = Column(String(50), nullable=False)
    filename = Column(String, nullable=False)
    input_path = Column(String, nullable=False)
    output_dir = Column(String, nullable=True)
    xml_path = Column(String, nullable=True)
    midi_path = Column(String, nullable=True)
    status = Column(String, nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    owner = relationship("User", back_populates="jobs")

    @property
    def xml_download_url(self) -> str | None:
        if self.status != "completed" or not self.xml_path:
            return None
        return f"/omr/download/xml/{self.job_id}"

    @property
    def midi_download_url(self) -> str | None:
        if self.status != "completed" or not self.midi_path:
            return None
        return f"/omr/download/midi/{self.job_id}"

    @property
    def pitch_image_url(self) -> str | None:
        if self.status != "completed" or not self.xml_path:
            return None

        xml_stem = Path(self.xml_path).stem
        pitch_abs_path = Path(self.output_dir or "") / f"{xml_stem}_pitch.png"
        if not pitch_abs_path.exists():
            return None

        return f"/outputs/{self.job_id}/{pitch_abs_path.name}"

    @property
    def teaser_image_url(self) -> str | None:
        if self.status != "completed" or not self.xml_path:
            return None

        xml_stem = Path(self.xml_path).stem
        teaser_abs_path = Path(self.output_dir or "") / f"{xml_stem}_teaser.png"
        if not teaser_abs_path.exists():
            return None

        return f"/outputs/{self.job_id}/{teaser_abs_path.name}"
