"""Grid-based annotation source for generating regular point grids."""

from typing import List, Optional
from shapely.geometry import Point, Polygon, MultiPolygon
import geopandas as gpd
from src.annotation.annotation import Annotation
from src.annotation.grid_generator import GridGenerator


class GridSource:
    """Annotation source that generates points from a regular grid."""
    
    def __init__(
        self,
        bbox: Optional[tuple] = None,  # (minx, miny, maxx, maxy) - optional if country polygon provided
        spacing: float = 0.01,
        start_id: int = 0,
        start_label: int = 0,
        country_polygon_path: Optional[str] = None,
        country_filter_column: Optional[str] = None,
        country_filter_value: Optional[str] = None
    ):
        """
        Initialize the grid source.
        
        Args:
            bbox: Optional bounding box as (minx, miny, maxx, maxy) in degrees.
                  If None and country polygon is provided, bbox will be calculated from polygon.
            spacing: Spacing between grid points in degrees
            start_id: Starting ID for generated points (default: 0)
            start_label: Starting label for generated points (default: 0)
            country_polygon_path: Optional path to country polygon shapefile
            country_filter_column: Optional column name to filter by (e.g., 'NAME', 'ISO_A3')
            country_filter_value: Optional value to filter by (e.g., 'France', 'FRA')
        """
        self.spacing = spacing
        self.start_id = start_id
        self.start_label = start_label
        self.country_polygon_path = country_polygon_path
        self.country_filter_column = country_filter_column
        self.country_filter_value = country_filter_value
        
        # Load country polygon if provided
        polygon_filter = None
        if country_polygon_path and country_filter_column and country_filter_value:
            polygon_filter = self._load_country_polygon(
                country_polygon_path,
                country_filter_column,
                country_filter_value
            )
            
            # If bbox not provided, calculate it from the polygon
            if bbox is None:
                # Get bounding box from polygon (minx, miny, maxx, maxy)
                bbox = polygon_filter.bounds
                print(f"Calculated bbox from country polygon: {bbox}")
            else:
                print(f"Using provided bbox: {bbox}")
                print(f"Note: Polygon filter will still be applied to exclude points outside country boundary")
        elif bbox is None:
            raise ValueError(
                "Either 'bbox' or 'country_polygon_path' with filter parameters must be provided"
            )
        
        self.bbox = bbox
        self.grid_generator = GridGenerator(
            bbox, spacing, start_id, start_label, polygon_filter=polygon_filter
        )
        self.annotation_source_type = 'grid'
        self.polygon_filter = polygon_filter
    
    def _load_country_polygon(
        self,
        polygon_path: str,
        filter_column: str,
        filter_value: str
    ) -> Optional[Polygon | MultiPolygon]:
        """
        Load country polygon from shapefile and filter by column value.
        
        Args:
            polygon_path: Path to polygon shapefile
            filter_column: Column name to filter by
            filter_value: Value to filter by
            
        Returns:
            Polygon or MultiPolygon geometry, or None if not found
        """
        try:
            # Load shapefile
            gdf = gpd.read_file(polygon_path)
            
            # Check if filter column exists
            if filter_column not in gdf.columns:
                available_cols = ', '.join(gdf.columns.tolist())
                raise ValueError(
                    f"Column '{filter_column}' not found in shapefile. "
                    f"Available columns: {available_cols}"
                )
            
            # Filter by column value
            filtered = gdf[gdf[filter_column] == filter_value]
            
            if len(filtered) == 0:
                # Try case-insensitive match
                filtered = gdf[gdf[filter_column].str.upper() == filter_value.upper()]
            
            if len(filtered) == 0:
                available_values = gdf[filter_column].unique()[:10].tolist()
                raise ValueError(
                    f"No matching country found for '{filter_value}' in column '{filter_column}'. "
                    f"Available values (first 10): {available_values}"
                )
            
            # Get the geometry (handle multiple matches by taking the first or union)
            if len(filtered) > 1:
                print(f"Warning: Multiple matches found for '{filter_value}'. Using union of all geometries.")
                geometry = filtered.geometry.unary_union
            else:
                geometry = filtered.geometry.iloc[0]
            
            # Ensure geometry is in WGS84 (EPSG:4326)
            if gdf.crs is None:
                print("Warning: Shapefile has no CRS. Assuming WGS84 (EPSG:4326).")
            elif gdf.crs.to_string() != 'EPSG:4326':
                print(f"Converting from {gdf.crs} to EPSG:4326...")
                filtered = filtered.to_crs('EPSG:4326')
                if len(filtered) > 1:
                    geometry = filtered.geometry.unary_union
                else:
                    geometry = filtered.geometry.iloc[0]
            
            print(f"Loaded country polygon: {filter_value} ({len(filtered)} feature(s))")
            return geometry
            
        except Exception as e:
            print(f"Error loading country polygon: {e}")
            raise
    
    def create_annotation_list(self) -> List[Annotation]:
        """
        Create a list of annotations from the grid.
        
        Returns:
            List of Annotation objects
        """
        points_data = self.grid_generator.generate_points()
        return [
            Annotation(
                id=str(point_id),
                label=str(label),
                annoted_object=point
            )
            for point, point_id, label in points_data
        ]
    
    def create_annotation_incremental(self):
        """
        Generator that yields annotations one by one (for incremental processing).
        
        Yields:
            Annotation objects
        """
        for point, point_id, label in self.grid_generator.generate_points_incremental():
            yield Annotation(
                id=str(point_id),
                label=str(label),
                annoted_object=point
            )
    
    def get_grid_info(self) -> dict:
        """
        Get information about the grid.
        
        Returns:
            Dictionary with grid information
        """
        info = self.grid_generator.get_grid_info()
        
        # Add country filter info
        if self.polygon_filter is not None:
            info['country_filter'] = {
                'polygon_path': self.country_polygon_path,
                'filter_column': self.country_filter_column,
                'filter_value': self.country_filter_value
            }
        
        return info

