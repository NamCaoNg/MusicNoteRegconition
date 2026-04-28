import os
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv

load_dotenv()

CORE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CORE_DIR.parent.parent

CHECKPOINTS_DIR = Path(os.getenv("CHECKPOINTS_DIR", str(PROJECT_ROOT / "checkpoints")))
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", str(PROJECT_ROOT / "outputs")))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(PROJECT_ROOT / "uploads")))
SKLEARN_MODELS_DIR = Path(os.getenv("SKLEARN_MODELS_DIR", str(PROJECT_ROOT / "sklearn_models")))

MYUNET_DIR = CHECKPOINTS_DIR / "MyUnet"
MYSEGNET_DIR = CHECKPOINTS_DIR / "MySegnet"

REQUIRED_CHECKPOINT_FILES: Tuple[Path, ...] = (
    MYUNET_DIR / "model.onnx",
    MYUNET_DIR / "metadata.pkl",
    MYSEGNET_DIR / "model.onnx",
    MYSEGNET_DIR / "metadata.pkl",
)

REQUIRED_SKLEARN_MODEL_FILES: Tuple[Path, ...] = (
    SKLEARN_MODELS_DIR / "accidental.model",
    SKLEARN_MODELS_DIR / "clef.model",
    SKLEARN_MODELS_DIR / "rests.model",
    SKLEARN_MODELS_DIR / "rests_above8.model",
)


def ensure_runtime_dirs() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    SKLEARN_MODELS_DIR.mkdir(parents=True, exist_ok=True)
