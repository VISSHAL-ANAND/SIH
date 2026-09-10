"""Memory-bounded U-Net inference for large SAR GeoTIFF scenes."""
from __future__ import annotations

from pathlib import Path
import numpy as np


def _prepare_tile(data: np.ndarray) -> np.ndarray:
    bands = data.shape[0]
    if bands == 1:
        data = np.repeat(data, 3, axis=0)
    elif bands == 2:
        data = np.concatenate([data, data[:1]], axis=0)
    else:
        data = data[:3]
    if data.dtype != np.uint8:
        finite = np.isfinite(data)
        values = data[finite]
        if values.size:
            lo, hi = np.percentile(values, (1.0, 99.0))
            if hi <= lo:
                hi = lo + 1.0
            data = np.clip((data - lo) * 255.0 / (hi - lo), 0, 255)
        else:
            data = np.zeros_like(data, dtype=np.float32)
        data = data.astype(np.uint8)
    return np.moveaxis(data, 0, -1)


def predict_mask_tiled(model, path: str | Path, predict_mask, *, tile_size: int = 1024, overlap: int = 128) -> np.ndarray:
    """Predict a whole raster without loading the complete scene as a model tensor."""
    if tile_size <= 0 or overlap < 0 or overlap >= tile_size:
        raise ValueError("tile_size must be > 0 and 0 <= overlap < tile_size")
    try:
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("rasterio is required for tiled GeoTIFF inference") from exc

    step = tile_size - overlap
    with rasterio.open(path) as src:
        if src.count < 1:
            raise ValueError("SAR raster contains no bands")
        output = np.zeros((src.height, src.width), dtype=np.uint16)
        votes = np.zeros((src.height, src.width), dtype=np.uint8)
        for y in range(0, src.height, step):
            for x in range(0, src.width, step):
                height = min(tile_size, src.height - y)
                width = min(tile_size, src.width - x)
                tile = _prepare_tile(src.read(window=Window(x, y, width, height)))
                pad_h = (-tile.shape[0]) % 32
                pad_w = (-tile.shape[1]) % 32
                if pad_h or pad_w:
                    tile = np.pad(tile, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
                mask = predict_mask(model, tile)[:height, :width]
                output[y:y+height, x:x+width] += mask.astype(np.uint16)
                votes[y:y+height, x:x+width] += 1
        return (output * 2 >= np.maximum(votes, 1)).astype(np.uint8)
