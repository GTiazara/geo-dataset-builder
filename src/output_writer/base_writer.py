from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import numpy as np


class ModalityOutput:
    """
    Container for modality output data and metadata.
    """
    def __init__(
        self,
        image: Image.Image,
        metadata: Dict[str, Any]
    ):
        """
        Initialize modality output.

        Args:
            image: PIL Image object.
            metadata: Dictionary containing metadata (bbox, crs, annotation info, etc.).
        """
        self.image = image
        self.metadata = metadata
    
    def get_image_array(self) -> np.ndarray:
        """
        Get image as numpy array.

        Returns:
            numpy array of the image.
        """
        return np.array(self.image)


class BaseWriter(ABC):
    """
    Base class for output writers.
    """
    def __init__(self, output_dir: str):
        """
        Initialize the output writer.

        Args:
            output_dir: Directory to save output files.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def write(self, output: ModalityOutput, annotation_id: str, annotation_label: str) -> Path:
        """
        Write the modality output to a file.

        Args:
            output: ModalityOutput containing image and metadata.
            annotation_id: Annotation ID.
            annotation_label: Annotation label.

        Returns:
            Path to the saved file.
        """
        pass
    
    def get_output_filename(self, annotation_id: str, annotation_label: str, extension: str) -> str:
        """
        Generate output filename.

        Args:
            annotation_id: Annotation ID.
            annotation_label: Annotation label.
            extension: File extension (without dot).

        Returns:
            Filename string.
        """
        return f"{annotation_id}_{annotation_label}.{extension}"

