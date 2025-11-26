import geopandas as gpd
import os 
import sys
from src.annotation.annotation import Annotation

class AnnotationSource:
    def __init__(self, path: str, id_column: str, label_column: str, annoted_object_column: str = 'geometry') -> None:
        """
        Initialize the annotation source.

        Args:
            path: The path to the annotation source. annotation source can be a shapefile or a geopackage or geojson of csv.
            id_column: The column name of the id.
            label_column: The column name of the label.
            annoted_object_column: The column name of the annoted object.
        """
        self.path = path
        self.id_column = id_column
        self.label_column = label_column
        self.annoted_object_column = annoted_object_column
        self.annotation_source_type = None
        self.data = self.load_data()
        
    def load_data(self) -> gpd.GeoDataFrame:
        """
        Load the annotation data from the source.

        Returns:
            gpd.GeoDataFrame: The annotation data.
        """
        # Validate file existence
        if not os.path.isfile(self.path):
            print(f"Error: File '{self.path}' not found.")
            sys.exit(1)
        # Load the data based on the file extension
        if self.path.endswith('.shp'):
            self.annotation_source_type = 'shp'
            return gpd.read_file(self.path)
        elif self.path.endswith('.gpkg'):
            self.annotation_source_type = 'gpkg'
            return gpd.read_file(self.path)
        elif self.path.endswith('.geojson'):
            self.annotation_source_type = 'geojson'
            return gpd.read_file(self.path)
        elif self.path.endswith('.csv'):
            self.annotation_source_type = 'csv'
            return gpd.read_file(self.path)
        else:
            print(f"Error: Unsupported file extension '{self.path}'.")
            sys.exit(1)
    
    def create_annoation_list(self) -> list:
        """
        Create a list of annotations from the source.

        Returns:
            list: The list of annotations.
        """
        return [
            Annotation(
                id=row[self.id_column], 
                label=row[self.label_column], 
                annoted_object=row[self.annoted_object_column]
            ) 
            for idx, row in self.data.iterrows()
        ]
    
 
    

