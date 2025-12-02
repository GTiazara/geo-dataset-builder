import sys
from pathlib import Path
from omegaconf import OmegaConf
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

# Add project root to path to enable imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.annotation.source import AnnotationSource
from src.annotation.grid_source import GridSource
from src.dataset_modality.factory import ModalityFactory
from src.output_writer import TIFWriter, HDF5Writer
from src.queue_manager import QueueManager


def _process_single_annotation(
    annotation,
    modality,
    writer,
    queue_manager,
    max_unprocessed
):
    """
    Process a single annotation and save the output.
    Helper function for parallel processing.
    
    Returns:
        Tuple of (success: bool, path: str or None, annotation_id: str)
    """
    try:
        # Wait if we have reached the maximum unprocessed limit
        if not queue_manager.can_produce():
            unprocessed_count = queue_manager.count_unprocessed()
            if unprocessed_count >= max_unprocessed:
                queue_manager.wait_until_can_produce()
        
        # Process the annotation
        output = modality.process_annotation(annotation)
        if not output:
            return (False, None, annotation.id)
        
        # Save the output
        path = writer.write(output, annotation.id, annotation.label)
        
        # Add to queue for consumer to process
        if queue_manager.add_output(str(path)):
            return (True, path, annotation.id)
        else:
            return (False, path, annotation.id)
    except Exception as e:
        print(f"Error processing annotation {annotation.id}: {e}")
        return (False, None, annotation.id)


def main(max_unprocessed: int = 10, queue_db_path: str = "output_queue.db", batch_size: int = 100, num_workers: int = 1):
    """
    Main producer function.
    
    Args:
        max_unprocessed: Maximum number of unprocessed outputs allowed (default: 10)
        queue_db_path: Path to queue database file (default: "output_queue.db")
        batch_size: Number of annotations to process in each batch (default: 100)
        num_workers: Number of parallel workers for processing annotations (default: 1, use 4-8 for I/O-bound tasks)
    """
    # Initialize queue manager for producer-consumer pattern
    queue_manager = QueueManager(db_path=queue_db_path, max_unprocessed=max_unprocessed)
    print(f"Queue manager initialized (max unprocessed: {max_unprocessed})")
    
    # Load configuration from conf.yaml (relative to project root)
    conf_path = project_root / "conf.yaml"
    conf = OmegaConf.load(str(conf_path))
    
    # Get batch size from config if available, otherwise use parameter
    config_batch_size = conf.get("batch_size", batch_size)
    if isinstance(config_batch_size, (int, float)):
        batch_size = int(config_batch_size)
    
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
            # Will process incrementally - annotation_list will be a generator
            annotation_list = None  # Will be set to generator during processing
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
            print(f"Output directory: {output_dir}")
            print(f"Batch size: {batch_size}")
            print(f"Number of workers: {num_workers}")
            if incremental:
                print(f"Processing mode: Incremental (one by one)\n")
            else:
                print(f"Total annotations: {len(annotation_list)}\n")
            
            # Process annotations in batches
            try:
                saved_paths = []
                
                # Handle incremental vs non-incremental processing
                if incremental:
                    # Incremental mode: use generator from source
                    annotation_generator = source.create_annotation_incremental()
                    
                    # For HDF5 format, we need to collect all outputs first
                    if output_format == "h5" or output_format == "hdf5":
                        # Process incrementally but collect all outputs
                        all_modality_outputs = []
                        annotation_count = 0
                        
                        for annotation in annotation_generator:
                            annotation_count += 1
                            output = modality.process_annotation(annotation)
                            if output:
                                all_modality_outputs.append((annotation, output))
                            
                            # Progress update every batch_size annotations
                            if annotation_count % batch_size == 0:
                                print(f"  Processed {annotation_count} annotations so far...")
                        
                        # Save all annotations in one HDF5 file
                        if all_modality_outputs:
                            path = writer.write_all(all_modality_outputs)
                            saved_paths.append(path)
                            print(f"\nSaved all {len(all_modality_outputs)} annotations to {path}")
                        print(f"Total annotations processed: {annotation_count}")
                    else:
                        # Other formats: process and save one file per annotation incrementally
                        annotation_count = 0
                        batch_saved = 0
                        
                        # Create process function with fixed parameters
                        process_func = partial(
                            _process_single_annotation,
                            modality=modality,
                            writer=writer,
                            queue_manager=queue_manager,
                            max_unprocessed=max_unprocessed
                        )
                        
                        if num_workers > 1:
                            # Parallel processing with ThreadPoolExecutor
                            # Process incrementally in small batches to maintain memory efficiency
                            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                                # Process in small batches from generator
                                batch_annotations = []
                                for annotation in annotation_generator:
                                    batch_annotations.append(annotation)
                                    
                                    # Process batch when we have enough workers' worth
                                    if len(batch_annotations) >= num_workers:
                                        # Submit batch
                                        futures = [executor.submit(process_func, ann) for ann in batch_annotations]
                                        
                                        # Process results as they complete
                                        for future in as_completed(futures):
                                            annotation_count += 1
                                            success, path, ann_id = future.result()
                                            
                                            if success and path:
                                                saved_paths.append(path)
                                                batch_saved += 1
                                                if (batch_saved % batch_size == 0) or (batch_saved % 10 == 0):
                                                    print(f"  Saved {batch_saved} annotations so far...")
                                        
                                        batch_annotations = []
                                
                                # Process remaining annotations
                                if batch_annotations:
                                    futures = [executor.submit(process_func, ann) for ann in batch_annotations]
                                    for future in as_completed(futures):
                                        annotation_count += 1
                                        success, path, ann_id = future.result()
                                        
                                        if success and path:
                                            saved_paths.append(path)
                                            batch_saved += 1
                                            if (batch_saved % batch_size == 0) or (batch_saved % 10 == 0):
                                                print(f"  Saved {batch_saved} annotations so far...")
                        else:
                            # Sequential processing (original behavior)
                            for annotation in annotation_generator:
                                annotation_count += 1
                                
                                # Wait if we have reached the maximum unprocessed limit
                                if not queue_manager.can_produce():
                                    unprocessed_count = queue_manager.count_unprocessed()
                                    print(f"  Waiting: {unprocessed_count} unprocessed outputs (max: {max_unprocessed})")
                                    queue_manager.wait_until_can_produce()
                                
                                # Process and save the output
                                output = modality.process_annotation(annotation)
                                if output:
                                    path = writer.write(output, annotation.id, annotation.label)
                                    saved_paths.append(path)
                                    
                                    # Add to queue for consumer to process
                                    if queue_manager.add_output(str(path)):
                                        batch_saved += 1
                                        if (batch_saved % batch_size == 0) or (batch_saved % 10 == 0):
                                            print(f"  Saved {batch_saved} annotations so far...")
                        
                        print(f"\nTotal annotations processed: {annotation_count}")
                        print(f"Total files saved: {batch_saved}")
                else:
                    # Non-incremental mode: use existing list-based processing
                    total_annotations = len(annotation_list)
                    num_batches = (total_annotations + batch_size - 1) // batch_size  # Ceiling division
                    
                    # For HDF5 format, we need to collect all outputs first
                    if output_format == "h5" or output_format == "hdf5":
                        # Process in batches but collect all outputs
                        all_modality_outputs = []
                        for batch_idx in range(num_batches):
                            start_idx = batch_idx * batch_size
                            end_idx = min(start_idx + batch_size, total_annotations)
                            batch_annotations = annotation_list[start_idx:end_idx]
                            
                            print(f"Processing batch {batch_idx + 1}/{num_batches} "
                                  f"(annotations {start_idx + 1}-{end_idx} of {total_annotations})")
                            
                            # Process batch
                            batch_outputs = []
                            for annotation in batch_annotations:
                                output = modality.process_annotation(annotation)
                                if output:
                                    batch_outputs.append((annotation, output))
                            
                            all_modality_outputs.extend(batch_outputs)
                            print(f"  Processed {len(batch_outputs)} annotations in this batch")
                        
                        # Save all annotations in one HDF5 file
                        if all_modality_outputs:
                            path = writer.write_all(all_modality_outputs)
                            saved_paths.append(path)
                            print(f"\nSaved all {len(all_modality_outputs)} annotations to {path}")
                    else:
                        # Other formats: process and save one file per annotation in batches
                        # Create process function with fixed parameters
                        process_func = partial(
                            _process_single_annotation,
                            modality=modality,
                            writer=writer,
                            queue_manager=queue_manager,
                            max_unprocessed=max_unprocessed
                        )
                        
                        if num_workers > 1:
                            # Parallel processing with ThreadPoolExecutor
                            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                                for batch_idx in range(num_batches):
                                    start_idx = batch_idx * batch_size
                                    end_idx = min(start_idx + batch_size, total_annotations)
                                    batch_annotations = annotation_list[start_idx:end_idx]
                                    
                                    print(f"Processing batch {batch_idx + 1}/{num_batches} "
                                          f"(annotations {start_idx + 1}-{end_idx} of {total_annotations})")
                                    
                                    # Submit all annotations in batch to executor
                                    future_to_annotation = {
                                        executor.submit(process_func, ann): ann
                                        for ann in batch_annotations
                                    }
                                    
                                    # Process completed futures as they finish
                                    batch_saved = 0
                                    for future in as_completed(future_to_annotation):
                                        success, path, ann_id = future.result()
                                        
                                        if success and path:
                                            saved_paths.append(path)
                                            batch_saved += 1
                                            if (batch_saved % 10 == 0) or (batch_saved == len(batch_annotations)):
                                                print(f"  Saved {batch_saved}/{len(batch_annotations)} in this batch "
                                                      f"(total: {len(saved_paths)}/{total_annotations})")
                                    
                                    print(f"  Completed batch {batch_idx + 1}/{num_batches}: "
                                          f"{batch_saved} files saved")
                        else:
                            # Sequential processing (original behavior)
                            for batch_idx in range(num_batches):
                                start_idx = batch_idx * batch_size
                                end_idx = min(start_idx + batch_size, total_annotations)
                                batch_annotations = annotation_list[start_idx:end_idx]
                                
                                print(f"Processing batch {batch_idx + 1}/{num_batches} "
                                      f"(annotations {start_idx + 1}-{end_idx} of {total_annotations})")
                                
                                batch_saved = 0
                                for annotation in batch_annotations:
                                    # Wait if we have reached the maximum unprocessed limit
                                    if not queue_manager.can_produce():
                                        unprocessed_count = queue_manager.count_unprocessed()
                                        print(f"  Waiting: {unprocessed_count} unprocessed outputs (max: {max_unprocessed})")
                                        queue_manager.wait_until_can_produce()
                                    
                                    # Process and save the output
                                    output = modality.process_annotation(annotation)
                                    if output:
                                        path = writer.write(output, annotation.id, annotation.label)
                                        saved_paths.append(path)
                                        
                                        # Add to queue for consumer to process
                                        if queue_manager.add_output(str(path)):
                                            batch_saved += 1
                                            if (batch_saved % 10 == 0) or (batch_saved == len(batch_annotations)):
                                                print(f"  Saved {batch_saved}/{len(batch_annotations)} in this batch "
                                                      f"(total: {len(saved_paths)}/{total_annotations})")
                                
                                print(f"  Completed batch {batch_idx + 1}/{num_batches}: "
                                      f"{batch_saved} files saved")
                
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
    import argparse
    
    parser = argparse.ArgumentParser(description="Producer program for generating outputs")
    parser.add_argument(
        "--max-unprocessed",
        type=int,
        default=10,
        help="Maximum number of unprocessed outputs allowed (default: 10)"
    )
    parser.add_argument(
        "--queue-db",
        type=str,
        default="output_queue.db",
        help="Path to queue database file (default: output_queue.db)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of annotations to process in each batch (default: 100)"
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=3,
        help="Number of parallel workers for processing annotations (default: 1, use 4-8 for I/O-bound tasks like tile downloading)"
    )
    
    args = parser.parse_args()
    
    main(
        max_unprocessed=args.max_unprocessed,
        queue_db_path=args.queue_db,
        batch_size=args.batch_size,
        num_workers=args.num_workers
    )

