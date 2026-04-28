import re
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

# Validation patterns
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,50}$")
# PASSWORD_PATTERN = re.compile(r"^[a-zA-Z0-9]{7,}$")
PASSWORD_PATTERN = re.compile(r"^.{8,128}$")
DISPLAY_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_ ]{1,50}$")

# Auth schemas
class UserRegister(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not USERNAME_PATTERN.match(v):
            raise ValueError(
                "Username must be 3-50 characters, only letters, digits, and underscores"
            )
        return v


    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not PASSWORD_PATTERN.match(v):
            raise ValueError("Password must be 8-128 characters")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Job schemas
class JobResponse(BaseModel):
    job_id: str
    display_name: str
    filename: str
    status: str
    xml_download_url: Optional[str] = None
    midi_download_url: Optional[str] = None
    pitch_image_url: Optional[str] = None
    teaser_image_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobResultResponse(BaseModel):
    job_id: str
    status: str
    teaser_image_url: Optional[str] = None
    pitch_image_url: Optional[str] = None
    xml_download_url: Optional[str] = None
    midi_download_url: Optional[str] = None
    xml_file_url: Optional[str] = None
    midi_file_url: Optional[str] = None
    xml_content: Optional[str] = None

    class Config:
        from_attributes = True


class JobResultRawResponse(BaseModel):
    job_id: str
    status: str
    teaser_image_mime_type: Optional[str] = None
    teaser_image_base64: Optional[str] = None
    pitch_image_mime_type: Optional[str] = None
    pitch_image_base64: Optional[str] = None
    xml_content: str
    midi_mime_type: str = "audio/midi"
    midi_base64: str

    class Config:
        from_attributes = True


class JobRename(BaseModel):
    new_name: str

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v: str) -> str:
        if not DISPLAY_NAME_PATTERN.match(v):
            raise ValueError(
                "Name must be 1-50 characters, only letters, digits, spaces, and underscores"
            )
        return v


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int = 1
    limit: int = 5
    total_pages: int = 1