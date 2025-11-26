from typing import List, Dict, Any
from omegaconf import DictConfig, OmegaConf
from src.annotation.annotation import Annotation
from src.dataset_modality.tms import TMSModality


class ModalityFactory:
    """
    Factory class for creating modality instances from configuration.
    """
    
    _modality_classes = {
        'tms': TMSModality,
    }
    
    @classmethod
    def create_modality(
        cls,
        modality_type: str,
        annotation_list: List[Annotation],
        config
    ):
        """
        Create a modality instance from configuration.

        Args:
            modality_type: Type of modality ('tms', etc.).
            annotation_list: List of annotations to process.
            config: Configuration dictionary for the modality.

        Returns:
            Modality instance.
        """
        modality_type_lower = modality_type.lower()
        
        if modality_type_lower not in cls._modality_classes:
            raise ValueError(
                f"Unknown modality type: {modality_type}. "
                f"Supported types: {list(cls._modality_classes.keys())}"
            )
        
        modality_class = cls._modality_classes[modality_type_lower]
        
        # Ensure config is a dict
        if not isinstance(config, dict):
            raise ValueError(f"Config must be a dict, got {type(config)}")
        
        # Create modality instance based on type
        if modality_type_lower == 'tms':
            return modality_class(
                annotation_list=annotation_list,
                bbox_size=config.get("bbox_size", 0.001),
                zoom_level=config.get("zoom_level", 18),
                tile_server=config.get("tile_server", "google")
            )
        else:
            # For future modalities, add their initialization here
            raise ValueError(f"Modality type {modality_type} not yet implemented in factory")
    
    @classmethod
    def register_modality(cls, name: str, modality_class):
        """
        Register a new modality type.

        Args:
            name: Name of the modality type.
            modality_class: Class of the modality.
        """
        cls._modality_classes[name.lower()] = modality_class

