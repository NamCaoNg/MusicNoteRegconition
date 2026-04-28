import os
import sys
import pickle
from pathlib import Path
from PIL import Image
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
from numpy import ndarray
import onnxruntime as rt

from src.core.config import SKLEARN_MODELS_DIR

from src.utils.logger import get_logger
logger = get_logger(__name__)


# Caches – tránh load lại model từ disk mỗi lần gọi
_onnx_cache: Dict[str, Tuple[rt.InferenceSession, dict]] = {}
_sklearn_cache: Dict[str, dict] = {}


def _get_session_options() -> rt.SessionOptions:
    """SessionOptions tối ưu cho 2 CPU cores."""
    opts = rt.SessionOptions()
    opts.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    opts.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
    return opts

def resize_image(image: Image.Image):
    w, h = image.size
    pis = w * h
    if 3000000 <= pis <= 3500000:
        return image
    lb = 3000000 / pis
    ub = 3500000 / pis
    ratio = pow((lb + ub) / 2, 0.5)
    tar_w = round(ratio * w)
    tar_h = round(ratio * h)
    # print(tar_w, tar_h)
    logger.info(f"Resize image to {tar_w}x{tar_h}")
    return image.resize((tar_w, tar_h))


def inference(
    model_path: str,
    img_path: str,
    step_size: int = 128,
    batch_size: int = 16,
    manual_th: Optional[Any] = None) -> Tuple[ndarray, ndarray]:

    onnx_path = os.path.join(model_path, "model.onnx")
    metadata_path = os.path.join(model_path, "metadata.pkl")

    if not os.path.exists(onnx_path):
        raise FileNotFoundError(f"Missing ONNX model: {onnx_path}")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Missing metadata file: {metadata_path}")

    # Lấy session + metadata từ cache, hoặc tạo mới lần đầu
    if onnx_path in _onnx_cache:
        sess, metadata = _onnx_cache[onnx_path]
    else:
        logger.info(f"Loading ONNX model (first time): {onnx_path}")
        with open(metadata_path, "rb") as f:
            metadata = pickle.load(f)

        available = rt.get_available_providers()
        if sys.platform == "darwin" and "CoreMLExecutionProvider" in available:
            providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        elif "CUDAExecutionProvider" in available:
            providers = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]

        logger.info(f"ONNX providers: {providers}")
        sess = rt.InferenceSession(onnx_path, sess_options=_get_session_options(), providers=providers)
        _onnx_cache[onnx_path] = (sess, metadata)

    input_name = metadata.get("input_name")
    if input_name is None:
        input_name = sess.get_inputs()[0].name

    output_names = metadata.get("output_names")
    if output_names is None:
        output_names = [out.name for out in sess.get_outputs()]

    input_shape = metadata["input_shape"]
    output_shape = metadata["output_shape"]

    # Collect data
    image_pil = Image.open(img_path)
    if "GIF" != image_pil.format:
        image_cv = cv2.imread(img_path)
        if image_cv is None:
            raise ValueError(f"Cannot read image: {img_path}")
        image_cv = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)
        image_pil = Image.fromarray(image_cv)

    image_pil = image_pil.convert("RGB")
    image = np.array(resize_image(image_pil))
    win_size = input_shape[1]

    data = []
    for y in range(0, image.shape[0], step_size):
        if y + win_size > image.shape[0]:
            y = image.shape[0] - win_size
        for x in range(0, image.shape[1], step_size):
            if x + win_size > image.shape[1]:
                x = image.shape[1] - win_size
            hop = image[y: y + win_size, x: x + win_size]
            data.append(hop)

    pred = []
    for idx in range(0, len(data), batch_size):
        # print(f"{idx + 1}/{len(data)} (step: {batch_size})", end="\r")
        if idx % (batch_size * 10) == 0:
            logger.info(f"Inference progress: {min(idx + batch_size, len(data))}/{len(data)}")
        batch = np.array(data[idx: idx + batch_size], dtype=np.float32)

        out = sess.run(output_names, {input_name: batch})[0]
        pred.append(out)

    output_shape = image.shape[:2] + (output_shape[-1],)
    out = np.zeros(output_shape, dtype=np.float32)
    mask = np.zeros(output_shape, dtype=np.float32)

    hop_idx = 0
    for y in range(0, image.shape[0], step_size):
        if y + win_size > image.shape[0]:
            y = image.shape[0] - win_size
        for x in range(0, image.shape[1], step_size):
            if x + win_size > image.shape[1]:
                x = image.shape[1] - win_size
            batch_idx = hop_idx // batch_size
            remainder = hop_idx % batch_size
            hop = pred[batch_idx][remainder]
            out[y: y + win_size, x: x + win_size] += hop
            mask[y: y + win_size, x: x + win_size] += 1
            hop_idx += 1

    out /= mask

    if manual_th is None:
        class_map = np.argmax(out, axis=-1)
    else:
        assert len(manual_th) == output_shape[-1] - 1, f"{manual_th}, {output_shape[-1]}"
        class_map = np.zeros(out.shape[:2] + (len(manual_th),))
        for idx, th in enumerate(manual_th):
            class_map[..., idx] = np.where(out[..., idx + 1] > th, 1, 0)

    return class_map, out


def predict(region: ndarray, model_name: str) -> str:
    if np.max(region) == 1:
        region *= 255

    # Lấy model từ cache, hoặc load lần đầu
    if model_name in _sklearn_cache:
        m_info = _sklearn_cache[model_name]
    else:
        model_path = os.path.join(str(SKLEARN_MODELS_DIR), f"{model_name}.model")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Missing sklearn model: {model_path}")
        logger.info(f"Loading sklearn model (first time): {model_name}")
        with open(model_path, "rb") as f:
            m_info = pickle.load(f)
        _sklearn_cache[model_name] = m_info

    model = m_info["model"]
    w = m_info["w"]
    h = m_info["h"]
    region = np.array(Image.fromarray(region.astype(np.uint8)).resize((w, h)))
    pred = model.predict(region.reshape(1, -1))
    return m_info["class_map"][pred[0]]


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    img_path = project_root / "data" / "myimages" / "Be_the_one01.jpg"
    model_path = project_root / "checkpoints" / "MyUnet"

    class_map, out = inference(str(model_path), str(img_path))

    color_map = np.zeros((class_map.shape[0], class_map.shape[1], 3), dtype=np.uint8)
    color_map[class_map == 0] = [0, 0, 0]
    color_map[class_map == 1] = [0, 0, 255]
    color_map[class_map == 2] = [0, 255, 0]
    color_map[class_map == 3] = [255, 0, 0]
    # color_map[class_map == 4] = [255, 255, 0]  # time signature — vàng
    # color_map[class_map == 5] = [255, 0, 255]  # beam — tím

    out_dir = project_root / "outputs" / "inferences"
    out_dir.mkdir(parents=True, exist_ok=True)

    save_path = out_dir / f"{img_path.stem}.png"
    Image.fromarray(color_map).save(str(save_path))
    logger.info(f"Saved to: {save_path}")