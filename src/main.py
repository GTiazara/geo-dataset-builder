import sys
from pathlib import Path
from omegaconf import OmegaConf

# Add project root to path to enable imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.annotation.source import AnnotationSource
from src.dataset_modality.factory import ModalityFactory
from src.output_writer import TIFWriter, HDF5Writer


def main():
    # Load configuration from conf.yaml (relative to project root)
    conf_path = project_root / "conf.yaml"
    conf = OmegaConf.load(str(conf_path))
    
    # Load shapefile source using configuration
    source = AnnotationSource(
        path=conf.source.path,
        id_column=conf.source.id_column,
        label_column=conf.source.label_column,
        annoted_object_column=conf.source.get("annoted_object_column", "geometry")
    )

    print(f"Loaded source from: {source.path}")
    print(f"Source type: {source.annotation_source_type}")
    print(f"Number of features: {len(source.data)}")
    
    # Create annotation list
    annotation_list = source.create_annoation_list()
    print(f"Created {len(annotation_list)} annotations")
    
    # Process annotations with modalities if configured
    modalities_config = []
    
    # Support both single modality (backward compatibility) and multiple modalities
    if hasattr(conf, 'modalities'):
        # New format: list of modalities
        # Convert OmegaConf ListConfig to regular list
        if isinstance(conf.modalities, list):
            modalities_config = list(conf.modalities)
        else:
            # Try to convert ListConfig to list
            try:
                converted = OmegaConf.to_container(conf.modalities, resolve=True)
                if isinstance(converted, list):
                    modalities_config = converted
                else:
                    # Single modality as dict
                    modalities_config = [converted] if converted else []
            except Exception:
                # Fallback: treat as single modality
                modalities_config = [conf.modalities]
    elif hasattr(conf, 'modality'):
        # Old format: single modality
        modalities_config = [conf.modality]
    
    print(f"Found {len(modalities_config)} modality/modalities to process")
    
    if modalities_config:
        total_saved = 0
        # Ensure we have a proper list to iterate over
        modalities_list = list(modalities_config) if not isinstance(modalities_config, list) else modalities_config
        
        for idx, modality_config in enumerate(modalities_list):
            # Convert to plain dict - handle both DictConfig and dict
            if isinstance(modality_config, dict):
                modality_dict = modality_config
            else:
                # Convert OmegaConf DictConfig to plain dict
                converted = OmegaConf.to_container(modality_config, resolve=True)
                if isinstance(converted, dict):
                    modality_dict = converted
                else:
                    # Fallback: build dict from attributes
                    modality_dict = {
                        "name": getattr(modality_config, 'name', f"modality_{idx+1}"),
                        "type": getattr(modality_config, 'type', 'tms'),
                        "bbox_size": getattr(modality_config, 'bbox_size', 0.001),
                        "zoom_level": getattr(modality_config, 'zoom_level', 18),
                        "tile_server": getattr(modality_config, 'tile_server', 'google')
                    }
            
            modality_name = modality_dict.get("name", f"modality_{idx+1}")
            modality_type = modality_dict.get("type", "tms")
            
            print(f"\n{'='*60}")
            print(f"Processing modality {idx+1}/{len(modalities_list)}: {modality_name} (type: {modality_type})")
            print(f"{'='*60}\n")
            
            # Create modality instance - pass plain dict
            try:
                modality = ModalityFactory.create_modality(
                    modality_type=modality_type,
                    annotation_list=annotation_list,
                    config=modality_dict
                )
            except Exception as e:
                print(f"Error creating modality {modality_name}: {e}")
                continue
            
            # Get output configuration (modality-specific or global)
            if "output" in modality_dict and modality_dict["output"]:
                # Modality-specific output config - convert to dict
                output_config_raw = modality_dict["output"]
                if isinstance(output_config_raw, dict):
                    output_config = output_config_raw
                else:
                    output_config = OmegaConf.to_container(output_config_raw, resolve=True) or {}
            elif hasattr(conf, 'output') and conf.output:
                # Global output config - convert to dict
                output_config_raw = conf.output
                if isinstance(output_config_raw, dict):
                    output_config = output_config_raw
                else:
                    output_config = OmegaConf.to_container(output_config_raw, resolve=True) or {}
            else:
                # Default output config
                output_config = {
                    "format": "tif",
                    "dir": "output",
                    "crs": "EPSG:4326",
                    "compress": "lzw"
                }
            
            # Ensure output_config is a dict
            if not isinstance(output_config, dict):
                output_config = {}
            
            output_format = output_config.get("format", "tif").lower()
            output_dir = output_config.get("dir", "output")
            
            # Add modality name to output directory to avoid conflicts
            if len(modalities_list) > 1:
                output_dir = f"{output_dir}/{modality_name}"
            
            crs = output_config.get("crs", "EPSG:4326")
            compress = output_config.get("compress", "lzw")
            
            # Create output writer
            if output_format == "tif" or output_format == "tiff":
                writer = TIFWriter(
                    output_dir=output_dir,
                    crs=crs,
                    compress=compress
                )
            elif output_format == "h5" or output_format == "hdf5":
                writer = HDF5Writer(output_dir=output_dir, modality_name=modality_name)
            else:
                print(f"Unsupported output format: {output_format}. Skipping modality {modality_name}")
                continue
            
            print(f"Output format: {output_format}")
            print(f"Output directory: {output_dir}\n")
            
            # Process all annotations
            try:
                modality_outputs = modality.process_all()
                
                # Write outputs using the writer
                saved_paths = []
                if output_format == "h5" or output_format == "hdf5":
                    # HDF5: save all annotations in one file
                    path = writer.write_all(modality_outputs)
                    saved_paths.append(path)
                    print(f"Saved all {len(modality_outputs)} annotations to {path}")
                else:
                    # Other formats: save one file per annotation
                    for annotation, output in modality_outputs:
                        path = writer.write(output, annotation.id, annotation.label)
                        saved_paths.append(path)
                        print(f"Saved output for annotation {annotation.id} to {path}")
                
                print(f"\nModality {modality_name}: Processed {len(saved_paths)} annotations and saved {len(saved_paths)} files")
                total_saved += len(saved_paths)
            except Exception as e:
                print(f"Error processing modality {modality_name}: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"Total: Processed {len(modalities_list)} modality/modalities and saved {total_saved} files")
        print(f"{'='*60}")
    
    return source


if __name__ == "__main__":
    main()

