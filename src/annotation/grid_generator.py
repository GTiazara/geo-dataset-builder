"""Grid generator for creating regular point grids over geographic areas."""

from typing import List, Tuple, Optional
from shapely.geometry import Point, Polygon, MultiPolygon
import numpy as np


class GridGenerator:
    """Generate a regular grid of points covering a geographic bounding box."""
    
    def __init__(
        self,
        bbox: Tuple[float, float, float, float],
        spacing: float,
        start_id: int = 0,
        start_label: int = 0,
        polygon_filter: Optional[Polygon | MultiPolygon] = None
    ):
        """
        Initialize the grid generator.
        
        Args:
            bbox: Bounding box as (minx, miny, maxx, maxy) in degrees
            spacing: Spacing between grid points in degrees
            start_id: Starting ID for generated points (default: 0)
            start_label: Starting label for generated points (default: 0)
            polygon_filter: Optional polygon to filter points (only points within polygon will be included)
        """
        self.bbox = bbox
        self.spacing = spacing
        self.start_id = start_id
        self.start_label = start_label
        self.polygon_filter = polygon_filter
        
        # Validate bbox
        minx, miny, maxx, maxy = bbox
        if minx >= maxx or miny >= maxy:
            raise ValueError(f"Invalid bbox: {bbox}. minx < maxx and miny < maxy required.")
        
        if spacing <= 0:
            raise ValueError(f"Spacing must be positive, got {spacing}")
    
    def generate_points(self) -> List[Tuple[Point, int, int]]:
        """
        Generate all grid points.
        
        Returns:
            List of tuples (Point, id, label) for each grid point
        """
        minx, miny, maxx, maxy = self.bbox
        
        # Calculate number of points in each direction
        # Add small epsilon to ensure we include points at the boundary
        num_x = int(np.ceil((maxx - minx) / self.spacing)) + 1
        num_y = int(np.ceil((maxy - miny) / self.spacing)) + 1
        
        points = []
        point_id = self.start_id
        
        # Generate grid points
        for i in range(num_y):
            y = miny + (i * self.spacing)
            # Clamp to bbox bounds
            if y > maxy:
                y = maxy
            
            for j in range(num_x):
                x = minx + (j * self.spacing)
                # Clamp to bbox bounds
                if x > maxx:
                    x = maxx
                
                point = Point(x, y)
                
                # Filter by polygon if provided
                if self.polygon_filter is None or self.polygon_filter.contains(point):
                    points.append((point, point_id, self.start_label))
                    point_id += 1
        
        return points
    
    def generate_points_incremental(self):
        """
        Generator that yields points one by one (for incremental processing).
        
        Yields:
            Tuples of (Point, id, label) for each grid point
        """
        minx, miny, maxx, maxy = self.bbox
        
        # Calculate number of points in each direction
        num_x = int(np.ceil((maxx - minx) / self.spacing)) + 1
        num_y = int(np.ceil((maxy - miny) / self.spacing)) + 1
        
        point_id = self.start_id
        
        # Generate grid points incrementally
        for i in range(num_y):
            y = miny + (i * self.spacing)
            # Clamp to bbox bounds
            if y > maxy:
                y = maxy
            
            for j in range(num_x):
                x = minx + (j * self.spacing)
                # Clamp to bbox bounds
                if x > maxx:
                    x = maxx
                
                point = Point(x, y)
                
                # Filter by polygon if provided
                if self.polygon_filter is None or self.polygon_filter.contains(point):
                    yield (point, point_id, self.start_label)
                    point_id += 1
    
    def get_grid_info(self) -> dict:
        """
        Get information about the grid that will be generated.
        
        Returns:
            Dictionary with grid information
        """
        minx, miny, maxx, maxy = self.bbox
        
        num_x = int(np.ceil((maxx - minx) / self.spacing)) + 1
        num_y = int(np.ceil((maxy - miny) / self.spacing)) + 1
        total_points = num_x * num_y
        
        # Calculate approximate area in square meters (at equator)
        width_deg = maxx - minx
        height_deg = maxy - miny
        width_m = width_deg * 111000  # Approximate meters per degree
        height_m = height_deg * 111000
        
        # Calculate filtered points if polygon filter is used
        filtered_points = total_points
        if self.polygon_filter is not None:
            # Estimate filtered points (approximate)
            # In practice, this will be calculated during generation
            filtered_points = None  # Will be calculated during actual generation
        
        return {
            'bbox': self.bbox,
            'spacing_degrees': self.spacing,
            'spacing_meters': self.spacing * 111000,  # Approximate
            'num_points_x': num_x,
            'num_points_y': num_y,
            'total_points': total_points,
            'filtered_points': filtered_points if filtered_points is not None else total_points,
            'has_polygon_filter': self.polygon_filter is not None,
            'area_degrees2': width_deg * height_deg,
            'area_km2': (width_m * height_m) / 1_000_000,
            'start_id': self.start_id,
            'start_label': self.start_label
        }
