import sys
from pathlib import Path
from omegaconf import OmegaConf

# Add project root to path to enable imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.annotation.source import AnnotationSource
from src.annotation.grid_source import GridSource
from src.dataset_modality.factory import ModalityFactory
from src.output_writer import TIFWriter, HDF5Writer


def main():
    # Load configuration from conf.yaml (relative to project root)
    conf_path = project_root / "conf.yaml"
    conf = OmegaConf.load(str(conf_path))
    
    # Check if grid generation mode is enabled
    use_grid = hasattr(conf, 'grid') and conf.grid is not None
    incremental = use_grid and conf.grid.get('incremental', False)
    grid_info = None  # Initialize for later use
    
    if use_grid:
        # Grid generation mode
        grid_config = conf.grid
        spacing = grid_config.spacing
        start_id = grid_config.get('start_id', 0)
        start_label = grid_config.get('start_label', 0)
        
        # Country polygon filtering (optional)
        country_polygon_path = grid_config.get('country_polygon_path', None)
        country_filter_column = grid_config.get('country_filter_column', None)
        country_filter_value = grid_config.get('country_filter_value', None)
        
        # Bbox is optional if country polygon is provided (will be calculated from polygon)
        bbox = None
        if hasattr(grid_config, 'bbox') and grid_config.bbox is not None:
            bbox = tuple(grid_config.bbox)  # (minx, miny, maxx, maxy)
        elif not (country_polygon_path and country_filter_column and country_filter_value):
            raise ValueError(
                "Either 'bbox' or 'country_polygon_path' with filter parameters must be provided in grid configuration"
            )
        
        source = GridSource(
            bbox=bbox,
            spacing=spacing,
            start_id=start_id,
            start_label=start_label,
            country_polygon_path=country_polygon_path,
            country_filter_column=country_filter_column,
            country_filter_value=country_filter_value
        )
        
        grid_info = source.get_grid_info()  # Store for later use
        print(f"{'='*60}")
        print("GRID GENERATION MODE")
        print(f"{'='*60}")
        
        # Show bbox source
        if bbox is None:
            print(f"Bounding box: {source.bbox} (calculated from country polygon)")
        else:
            print(f"Bounding box: {source.bbox}")
            if country_polygon_path:
                print(f"  Note: Using provided bbox, but polygon filter will exclude points outside country")
        
        print(f"Spacing: {spacing}° ({grid_info['spacing_meters']:.1f} m)")
        print(f"Grid size: {grid_info['num_points_x']} x {grid_info['num_points_y']} points")
        print(f"Total points in bbox: {grid_info['total_points']}")
        
        # Show country filter info if present
        if 'country_filter' in grid_info and grid_info['country_filter']:
            cf = grid_info['country_filter']
            print(f"Country filter: {cf['filter_value']} (column: {cf['filter_column']})")
            print(f"  Polygon file: {cf['polygon_path']}")
            print(f"  Note: Only points within country boundary will be generated")
            print(f"  This ensures all islands and territories are included")
        
        print(f"Coverage area: {grid_info['area_km2']:.2f} km²")
        print(f"Incremental processing: {incremental}")
        print(f"{'='*60}\n")
        
        if not incremental:
            # Create all annotations at once
            annotation_list = source.create_annotation_list()
            print(f"Created {len(annotation_list)} annotations from grid\n")
        else:
            # Will process incrementally
            annotation_list = None
            print("Will process points incrementally (one by one)\n")
    else:
        # Normal mode: load from file
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
            
            # Process annotations
            try:
                if incremental and use_grid:
                    # Incremental processing: process one point at a time
                    saved_paths = []
                    processed_count = 0
                    
                    print("Starting incremental processing...\n")
                    for annotation in source.create_annotation_incremental():
                        processed_count += 1
                        print(f"Processing point {processed_count}/{grid_info['total_points']}: ID={annotation.id} at ({annotation.annoted_object.x:.6f}, {annotation.annoted_object.y:.6f})")
                        
                        # Process single annotation
                        try:
                            # Create a temporary modality with just this annotation
                            temp_modality = ModalityFactory.create_modality(
                                modality_type=modality_type,
                                annotation_list=[annotation],
                                config=modality_dict
                            )
                            
                            # Process the single annotation
                            modality_outputs = temp_modality.process_all()
                            
                            if modality_outputs:
                                annotation_result, output = modality_outputs[0]
                                
                                # Write output
                                if output_format == "h5" or output_format == "hdf5":
                                    # For HDF5, we need to accumulate and write at the end
                                    # For now, save individually (could be optimized)
                                    path = writer.write(output, annotation.id, annotation.label)
                                    saved_paths.append(path)
                                else:
                                    # TIF: save one file per annotation
                                    path = writer.write(output, annotation.id, annotation.label)
                                    saved_paths.append(path)
                                    print(f"  ✓ Saved to {path}")
                                print()
                            else:
                                print(f"  ✗ No output generated for this point\n")
                        except Exception as e:
                            print(f"  ✗ Error processing point {annotation.id}: {e}\n")
                            continue
                    
                    # For HDF5 in incremental mode, we might want to write all at once
                    # But for now, we write individually
                    print(f"\nModality {modality_name}: Processed {processed_count} points and saved {len(saved_paths)} files")
                    total_saved += len(saved_paths)
                else:
                    # Batch processing: process all annotations at once
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
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*60}")
        print(f"Total: Processed {len(modalities_list)} modality/modalities and saved {total_saved} files")
        print(f"{'='*60}")
    
    return source


if __name__ == "__main__":
    main()

