from pathlib import Path
from typing import Dict, Any
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
from src.output_writer.base_writer import BaseWriter, ModalityOutput


class TIFWriter(BaseWriter):
    """
    Writer for GeoTIFF format.
    """
    def __init__(self, output_dir: str, crs: str = "EPSG:4326", compress: str = "lzw"):
        """
        Initialize TIF writer.

        Args:
            output_dir: Directory to save output files.
            crs: Coordinate reference system (default: EPSG:4326).
            compress: Compression method (default: lzw).
        """
        super().__init__(output_dir)
        self.crs = crs
        self.compress = compress
    
    def write(self, output: ModalityOutput, annotation_id: str, annotation_label: str) -> Path:
        """
        Write the modality output as a GeoTIFF.

        Args:
            output: ModalityOutput containing image and metadata.
            annotation_id: Annotation ID.
            annotation_label: Annotation label.

        Returns:
            Path to the saved TIFF file.
        """
        # Get bbox from metadata
        bbox = output.metadata.get('bbox')
        if bbox is None:
            raise ValueError("Metadata must contain 'bbox' key with (minx, miny, maxx, maxy)")
        
        minx, miny, maxx, maxy = bbox
        image = output.image
        width, height = image.size
        
        # Create transform from bounds
        transform = from_bounds(minx, miny, maxx, maxy, width, height)
        
        # Convert PIL image to numpy array
        img_array = np.array(image)
        
        # Handle RGB vs grayscale
        if len(img_array.shape) == 3:
            # RGB image - need to transpose from (H, W, C) to (C, H, W)
            img_array = img_array.transpose(2, 0, 1)
            count = 3
        else:
            count = 1
        
        # Generate output filename
        output_filename = self.get_output_filename(annotation_id, annotation_label, "tif")
        output_path = self.output_dir / output_filename
        
        # Save as GeoTIFF
        with rasterio.open(
            output_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=count,
            dtype=img_array.dtype,
            crs=self.crs,
            transform=transform,
            compress=self.compress
        ) as dst:
            if count == 3:
                dst.write(img_array)
            else:
                dst.write(img_array, 1)
        
        return output_path

