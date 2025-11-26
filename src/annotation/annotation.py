import geopandas as gpd

class Annotation:
    def __init__(self, id: str, label: str, annoted_object: list) -> None:
        """
        Initialize the annotation.

        Args:
            data: The annotation data.
        """
        self.id = id
        self.label = label
        self.annoted_object = annoted_object
    
    def get_annoted_object_type(self) -> str:
        """
        Get the type of the annoted object.

        Returns:
            str: The type of the annoted object.
        """
        return self.annoted_object.type

    def __str__(self) -> str:
        """
        Return a string representation of the annotation.

        Returns:
            str: The string representation of the annotation.
        """
        return f"Annotation(id={self.id}, label={self.label}, annoted_object={self.annoted_object})"
    
    def __repr__(self) -> str:
        """
        Return a string representation of the annotation.

        Returns:
            str: The string representation of the annotation.
        """
        return self.__str__()