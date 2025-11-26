from mercantile import Tile
import os
import time
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import mercantile
import requests
from PIL import Image
import io
import numpy as np
from shapely.geometry import Point
from src.annotation.annotation import Annotation
from src.output_writer.base_writer import ModalityOutput


class TMSModality:
    def __init__(
        self, 
        annotation_list: List[Annotation],
        bbox_size: float = 0.001,  # Size in degrees (approximately 111m per 0.001 degree)
        zoom_level: int = 18,
        tile_server: str = "google"
    ) -> None:
        """
        Initialize the TMS (Tile Map Service) modality.

        Args:
            annotation_list: The list of annotations.
            bbox_size: Size of the bounding box in degrees (default: 0.001, ~111m).
            zoom_level: Zoom level for tile requests (default: 18).
            tile_server: Tile server to use ('google', 'osm', or custom URL template).
        """
        self.annotation_list = annotation_list
        self.bbox_size = bbox_size
        self.zoom_level = zoom_level
        self.tile_server = tile_server
        
        # Tile server URL templates
        self.tile_urls = {
            "google": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        }
        
        # Rate limiting: delays between requests (good practice for all servers)
        # OSM requires max 2 requests per second (0.5s delay)
        # Other servers: smaller delay to be respectful but not too slow
        self.tile_delay = 0.5 if tile_server == "osm" else 0.1
        self.last_request_time = 0
        
        # User-Agent header (required by OSM usage policy, good practice for others)
        self.user_agent = "geo-dataset-maker/0.1.0" if tile_server == "osm" else "Mozilla/5.0"
        
        # Calculate target image size in pixels for consistent output
        # At zoom level Z, one tile (256px) covers: 360 / (2^Z) degrees
        # For bbox_size degrees, we need: (bbox_size / (360 / 2^Z)) * 256 pixels
        degrees_per_tile = 360.0 / (2 ** zoom_level)
        self.target_size_pixels = int((bbox_size / degrees_per_tile) * 256)
    
    def create_bbox_from_point(self, point: Point) -> Tuple[float, float, float, float]:
        """
        Create a bounding box around a point.

        Args:
            point: Shapely Point geometry.

        Returns:
            Tuple of (minx, miny, maxx, maxy) bounding box coordinates.
        """
        half_size = self.bbox_size / 2.0
        minx = point.x - half_size
        maxx = point.x + half_size
        miny = point.y - half_size
        maxy = point.y + half_size
        print(f"Bounding box: {minx}, {miny}, {maxx}, {maxy}")
        return (minx, miny, maxx, maxy)
    
    def get_tiles_for_bbox(self, bbox: Tuple[float, float, float, float]) -> List[mercantile.Tile]:
        """
        Get all tiles that intersect with the bounding box.

        Args:
            bbox: Bounding box as (minx, miny, maxx, maxy).

        Returns:
            List of mercantile Tile objects.
        """
        minx, miny, maxx, maxy = bbox
        tiles = list(mercantile.tiles(minx, miny, maxx, maxy, zooms=self.zoom_level))
        print(f"Tiles: {tiles}")
        return tiles
    
    def download_tile(self, tile: mercantile.Tile) -> Image.Image:
        """
        Download a single tile from the tile server.

        Args:
            tile: Mercantile Tile object.

        Returns:
            PIL Image object.
        """
        # Rate limiting: respect tile server usage policies
        elapsed = time.time() - self.last_request_time
        if elapsed < self.tile_delay:
            time.sleep(self.tile_delay - elapsed)
        self.last_request_time = time.time()
        
        if self.tile_server in self.tile_urls:
            url = self.tile_urls[self.tile_server].format(x=tile.x, y=tile.y, z=tile.z)
        else:
            # Assume custom URL template
            url = self.tile_server.format(x=tile.x, y=tile.y, z=tile.z)
        
        # Set headers (required by OSM usage policy)
        headers = {'User-Agent': self.user_agent}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content))
            return img
        except Exception as e:
            print(f"Error downloading tile {tile}: {e}")
            # Return a blank tile if download fails
            return Image.new('RGB', (256, 256), color='gray')
    
    def merge_tiles_to_image(self, tiles: List[mercantile.Tile]) -> Tuple[Image.Image, Tuple[float, float, float, float]]:
        """
        Merge multiple tiles into a single image.

        Args:
            tiles: List of mercantile Tile objects.

        Returns:
            Tuple of (merged PIL Image, bounding box as minx, miny, maxx, maxy).
        """
        if not tiles:
            raise ValueError("No tiles provided")
        
        # Get bounding box of all tiles
        tile_bboxes = [mercantile.bounds(tile) for tile in tiles]
        minx = min(b.west for b in tile_bboxes)
        miny = min(b.south for b in tile_bboxes)
        maxx = max(b.east for b in tile_bboxes)
        maxy = max(b.north for b in tile_bboxes)
        
        # Find tile coordinate ranges
        x_coords = sorted(set(tile.x for tile in tiles))
        y_coords = sorted(set(tile.y for tile in tiles))
        
        min_x_tile = min(x_coords)
        max_x_tile = max(x_coords)
        min_y_tile = min(y_coords)
        max_y_tile = max(y_coords)
        
        # Calculate image dimensions
        tile_width = 256
        tile_height = 256
        img_width = (max_x_tile - min_x_tile + 1) * tile_width
        img_height = (max_y_tile - min_y_tile + 1) * tile_height
        
        # Create merged image
        merged_img = Image.new('RGB', (img_width, img_height))
        
        # Download and paste tiles
        for tile in tiles:
            img = self.download_tile(tile)
            x_offset = (tile.x - min_x_tile) * tile_width
            y_offset = (tile.y - min_y_tile) * tile_height
            merged_img.paste(img, (x_offset, y_offset))
        
        # Crop/resize to consistent target size (centered)
        if merged_img.width != self.target_size_pixels or merged_img.height != self.target_size_pixels:
            # Calculate crop box (center crop)
            crop_x = (merged_img.width - self.target_size_pixels) // 2
            crop_y = (merged_img.height - self.target_size_pixels) // 2
            crop_box = (
                crop_x,
                crop_y,
                crop_x + self.target_size_pixels,
                crop_y + self.target_size_pixels
            )
            
            # Crop to target size
            if crop_x >= 0 and crop_y >= 0 and crop_box[2] <= merged_img.width and crop_box[3] <= merged_img.height:
                merged_img = merged_img.crop(crop_box)
            else:
                # If crop box is out of bounds, resize instead
                merged_img = merged_img.resize((self.target_size_pixels, self.target_size_pixels), Image.Resampling.LANCZOS)
        
        # Recalculate bbox to match the cropped/resized image
        # The bbox should represent the actual geographic area of the final image
        # Since we're cropping from center, adjust the bbox accordingly
        center_x = (minx + maxx) / 2.0
        center_y = (miny + maxy) / 2.0
        half_size = self.bbox_size / 2.0
        final_bbox = (
            center_x - half_size,
            center_y - half_size,
            center_x + half_size,
            center_y + half_size
        )
        
        return merged_img, final_bbox
    
    def process_annotation(self, annotation: Annotation) -> Optional[ModalityOutput]:
        """
        Process a single annotation: create bbox, download tiles, return image and metadata.

        Args:
            annotation: Annotation object.

        Returns:
            ModalityOutput containing image and metadata, or None if processing fails.
        """
        # Check if geometry is a Point
        if not isinstance(annotation.annoted_object, Point):
            print(f"Annotation {annotation.id} is not a Point, skipping...")
            return None
        
        # Create bbox around point
        bbox = self.create_bbox_from_point(annotation.annoted_object)
        
        # Get tiles for bbox
        tiles = self.get_tiles_for_bbox(bbox)
        
        if not tiles:
            print(f"No tiles found for annotation {annotation.id}")
            return None
        
        # Merge tiles into single image
        merged_image, tile_bbox = self.merge_tiles_to_image(tiles)
        
        # Create metadata
        metadata: Dict[str, Any] = {
            'bbox': tile_bbox,  # (minx, miny, maxx, maxy)
            'crs': 'EPSG:4326',
            'zoom_level': self.zoom_level,
            'tile_server': self.tile_server,
            'bbox_size': self.bbox_size,
            'annotation_id': annotation.id,
            'annotation_label': annotation.label,
            'geometry_type': 'Point',
            'point_coords': (annotation.annoted_object.x, annotation.annoted_object.y)
        }
        
        return ModalityOutput(image=merged_image, metadata=metadata)
    
    def process_all(self) -> List[Tuple[Annotation, ModalityOutput]]:
        """
        Process all annotations in the list.

        Returns:
            List of tuples (Annotation, ModalityOutput).
        """
        outputs = []
        for annotation in self.annotation_list:
            output = self.process_annotation(annotation)
            if output:
                outputs.append((annotation, output))
        return outputs

