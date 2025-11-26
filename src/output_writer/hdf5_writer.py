from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import h5py
from PIL import Image
from src.output_writer.base_writer import BaseWriter, ModalityOutput
from src.annotation.annotation import Annotation


class HDF5Writer(BaseWriter):
    """
    Writer for HDF5 format.
    Saves all annotations in a single HDF5 file per modality.
    """
    def __init__(self, output_dir: str, modality_name: str = "modality"):
        """
        Initialize HDF5 writer.

        Args:
            output_dir: Directory to save output files.
            modality_name: Name of the modality (used for filename).
        """
        super().__init__(output_dir)
        self.modality_name = modality_name
    
    def write(self, output: ModalityOutput, annotation_id: str, annotation_label: str) -> Path:
        """
        Write method for compatibility, but HDF5 should use write_all instead.
        This method is kept for interface compatibility but will accumulate data.

        Args:
            output: ModalityOutput containing image and metadata.
            annotation_id: Annotation ID.
            annotation_label: Annotation label.

        Returns:
            Path to the saved HDF5 file (will be created when write_all is called).
        """
        # For HDF5, we should use write_all instead
        # This is kept for interface compatibility
        raise NotImplementedError("HDF5Writer should use write_all() method to save all annotations in one file")
    
    def write_all(self, annotations_outputs: List[Tuple[Annotation, ModalityOutput]]) -> Path:
        """
        Write all annotations to a single HDF5 file.

        Args:
            annotations_outputs: List of tuples (Annotation, ModalityOutput).

        Returns:
            Path to the saved HDF5 file.
        """
        if not annotations_outputs:
            raise ValueError("No annotations to write")
        
        # Generate output filename based on modality name
        output_filename = f"{self.modality_name}.h5"
        output_path = self.output_dir / output_filename
        
        # Save all annotations in one HDF5 file with simple structure
        with h5py.File(output_path, 'w') as f:
            # Create img group
            img_group = f.create_group('img')
            
            for annotation, output in annotations_outputs:
                # Use same naming convention as image files: {id}_{label}
                dataset_name = f"{annotation.id}_{annotation.label}"
                
                # Convert PIL image to numpy array (same as TIF writer)
                img_array = np.array(output.image)
                
                # Ensure array is contiguous
                if not img_array.flags['C_CONTIGUOUS']:
                    img_array = np.ascontiguousarray(img_array)
                
                # Create dataset for this annotation's image
                img_group.create_dataset(dataset_name, data=img_array, compression='gzip')
                
                # Store bbox from metadata
                bbox = output.metadata.get('bbox', [0, 0, 0, 0])
                img_group[dataset_name].attrs['bbox'] = bbox
                
                # Store other metadata as attributes
                for key, value in output.metadata.items():
                    if key != 'bbox' and isinstance(value, (str, int, float, bool)):
                        img_group[dataset_name].attrs[key] = value
                    elif key != 'bbox' and isinstance(value, (list, tuple)):
                        # Store lists/tuples as arrays
                        img_group[dataset_name].attrs[key] = np.array(value)
            
            # Store attributes on the group
            img_group.attrs['num_annotations'] = len(annotations_outputs)
            img_group.attrs['modality_name'] = self.modality_name
        
        return output_path

