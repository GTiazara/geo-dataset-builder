"""Calculate bbox size for desired image resolution."""

def calculate_bbox_for_resolution(target_width: int, target_height: int, zoom_level: int = 18):
    """
    Calculate the bbox size (in degrees) needed to achieve a target pixel resolution.
    
    Formula:
    - At zoom level Z, one tile (256px) covers: 360 / (2^Z) degrees
    - For target pixels, bbox_size = (target_pixels / 256) * (360 / 2^Z)
    
    Args:
        target_width: Desired image width in pixels
        target_height: Desired image height in pixels
        zoom_level: Zoom level for tile requests (default: 18)
    
    Returns:
        Dictionary with calculated bbox sizes and information
    """
    # Calculate degrees per tile at this zoom level
    degrees_per_tile = 360.0 / (2 ** zoom_level)
    
    # Calculate bbox size for width and height
    bbox_width = (target_width / 256.0) * degrees_per_tile
    bbox_height = (target_height / 256.0) * degrees_per_tile
    
    # For square bbox (current implementation), use the larger dimension
    bbox_size_square = max(bbox_width, bbox_height)
    
    # Calculate meters (approximate: 1 degree ≈ 111,000 meters at equator)
    bbox_width_m = bbox_width * 111000
    bbox_height_m = bbox_height * 111000
    bbox_size_square_m = bbox_size_square * 111000
    
    return {
        'zoom_level': zoom_level,
        'target_resolution': f"{target_width}x{target_height}",
        'degrees_per_tile': degrees_per_tile,
        'bbox_width_degrees': bbox_width,
        'bbox_height_degrees': bbox_height,
        'bbox_size_square_degrees': bbox_size_square,
        'bbox_width_meters': bbox_width_m,
        'bbox_height_meters': bbox_height_m,
        'bbox_size_square_meters': bbox_size_square_m,
        'aspect_ratio': target_width / target_height,
    }


if __name__ == "__main__":
    # Calculate for HRPlanes dataset resolution: 4800x2703
    target_width = 4800
    target_height = 2703
    zoom_level = 18
    
    print("=" * 70)
    print(f"Bbox Size Calculation for {target_width}x{target_height} pixels")
    print(f"Zoom Level: {zoom_level}")
    print("=" * 70)
    
    result = calculate_bbox_for_resolution(target_width, target_height, zoom_level)
    
    print(f"\nDegrees per tile at zoom {zoom_level}: {result['degrees_per_tile']:.6f}°")
    print(f"\nFor rectangular bbox (to match exact resolution):")
    print(f"  Width:  {result['bbox_width_degrees']:.6f}° ({result['bbox_width_meters']:.1f} m)")
    print(f"  Height: {result['bbox_height_degrees']:.6f}° ({result['bbox_height_meters']:.1f} m)")
    print(f"\nFor square bbox (current implementation - uses larger dimension):")
    print(f"  Size:   {result['bbox_size_square_degrees']:.6f}° ({result['bbox_size_square_meters']:.1f} m)")
    print(f"\nAspect ratio: {result['aspect_ratio']:.2f}:1 (16:9 ≈ {16/9:.2f}:1)")
    
    print("\n" + "=" * 70)
    print("RECOMMENDATION:")
    print("=" * 70)
    print(f"Use bbox_size: {result['bbox_size_square_degrees']:.6f} in your conf.yaml")
    print(f"(This will give you approximately {target_width}x{target_width} pixels)")
    print("\nNote: Current implementation creates square images.")
    print("To get exact 4800x2703, you would need to modify the code to support")
    print("rectangular bboxes (bbox_width and bbox_height separately).")




