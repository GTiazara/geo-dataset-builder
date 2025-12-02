# Grid Generation Feature

This feature allows you to generate a regular grid of points covering a geographic area and process each point to create satellite imagery.

## Configuration

To use grid generation mode, add a `grid` section to your `conf.yaml` file instead of (or in addition to) the `source` section:

```yaml
grid:
  bbox: [minx, miny, maxx, maxy]  # Bounding box in degrees (optional if country polygon provided)
  spacing: 0.01  # Spacing between points in degrees
  start_id: 0  # Optional: starting ID (default: 0)
  start_label: 0  # Optional: label for all points (default: 0)
  incremental: true  # Optional: process one by one (default: false)
  # Country polygon filtering (optional):
  # When using country polygon, bbox is automatically calculated from the polygon
  # This ensures all islands and territories are included
  country_polygon_path: "path/to/countries.shp"  # Path to country polygon shapefile
  country_filter_column: "NAME"  # Column name (e.g., "NAME", "ISO_A3", "ISO_A2")
  country_filter_value: "France"  # Country name or code to filter by
```

### Parameters

- **bbox**: Bounding box as `[minx, miny, maxx, maxy]` in degrees (longitude, latitude)
  - **Optional** when using country polygon - will be automatically calculated from the polygon
  - **Required** when not using country polygon
  - Example for France: `[-5.0, 41.0, 9.0, 51.0]`
  - Example for Paris region: `[2.0, 48.5, 2.5, 49.0]`
  - When country polygon is provided, the polygon's bbox is used automatically (ensures all islands/territories are included)

- **spacing**: Distance between grid points in degrees
  - `0.01` degrees ≈ 1.1 km at equator
  - `0.001` degrees ≈ 111 m at equator
  - `0.0001` degrees ≈ 11 m at equator

- **start_id**: Starting ID number for generated points (default: 0)

- **start_label**: Label value for all generated points (default: 0)

- **incremental**: Processing mode
  - `true`: Process points one by one (generates and processes immediately)
  - `false`: Generate all points first, then process in batch

- **country_polygon_path**: (Optional) Path to country polygon shapefile
  - If provided, only points within the country boundary will be generated
  - Requires `country_filter_column` and `country_filter_value`

- **country_filter_column**: (Optional) Column name in shapefile to filter by
  - Common options: `"NAME"`, `"ISO_A3"`, `"ISO_A2"`, `"NAME_EN"`
  - Check your shapefile to see available columns

- **country_filter_value**: (Optional) Value to filter by
  - Country name (e.g., `"France"`) or ISO code (e.g., `"FRA"`)
  - Must match a value in the specified column

## Examples

### Example 1: Small area with fine grid (incremental)

```yaml
grid:
  bbox: [2.0, 48.5, 2.5, 49.0]  # Paris region
  spacing: 0.01  # ~1.1 km spacing
  incremental: true

modalities:
  - name: "google_maps"
    type: "tms"
    bbox_size: 0.025749
    zoom_level: 18
    tile_server: "google"
```

### Example 2: Large area with coarse grid (batch)

```yaml
grid:
  bbox: [-5.0, 41.0, 9.0, 51.0]  # France
  spacing: 0.1  # ~11 km spacing
  incremental: false

modalities:
  - name: "google_maps"
    type: "tms"
    bbox_size: 0.025749
    zoom_level: 18
    tile_server: "google"
```

### Example 3: Grid with country polygon filter (bbox calculated automatically - RECOMMENDED)

```yaml
grid:
  # bbox is optional - will be automatically calculated from the country polygon
  # This ensures all islands and territories are included
  spacing: 0.1  # ~11 km spacing
  incremental: true
  country_polygon_path: "data/countries.shp"  # Path to country shapefile
  country_filter_column: "NAME"  # Column containing country names
  country_filter_value: "France"  # Filter for France only

modalities:
  - name: "google_maps"
    type: "tms"
    bbox_size: 0.025749
    zoom_level: 18
    tile_server: "google"
```

### Example 4: Grid with ISO code filter (bbox calculated automatically)

```yaml
grid:
  # bbox is optional - automatically calculated from polygon
  spacing: 0.1
  incremental: true
  country_polygon_path: "data/countries.shp"
  country_filter_column: "ISO_A3"  # ISO 3-letter code column
  country_filter_value: "FRA"  # France ISO code

modalities:
  - name: "google_maps"
    type: "tms"
    bbox_size: 0.025749
    zoom_level: 18
    tile_server: "google"
```

## Usage

1. Configure your `conf.yaml` with the `grid` section
2. Run the program:
   ```bash
   python src/main.py
   ```

The program will:
1. Calculate the grid dimensions and total number of points
2. Generate points according to the spacing
3. Process each point with the configured modalities
4. Save images for each point

## Grid Information

When you run the program, it will display:
- Bounding box
- Spacing in degrees and meters
- Grid size (number of points in X and Y directions)
- Total number of points
- Coverage area in km²
- Processing mode (incremental or batch)

## Incremental vs Batch Processing

### Incremental Mode (`incremental: true`)
- Generates one point at a time
- Processes each point immediately after generation
- Better for:
  - Large grids where you want to see progress
  - Memory-constrained environments
  - Long-running processes where you want early results

### Batch Mode (`incremental: false`)
- Generates all points first
- Then processes all points together
- Better for:
  - Small grids
  - When you need all points before processing
  - Faster overall processing for small datasets

## Country Polygon Filtering

You can filter grid points to only those within a specific country's boundary by providing a country polygon shapefile:

1. **Prepare your shapefile**: You need a polygon shapefile containing country boundaries
   - Common sources: Natural Earth, GADM, World Bank
   - Must be in WGS84 (EPSG:4326) or will be automatically converted

2. **Identify the filter column**: Check your shapefile to find the column containing country names or codes
   - Common columns: `NAME`, `ISO_A3`, `ISO_A2`, `NAME_EN`
   - Use `ogrinfo` or load in QGIS to inspect columns

3. **Configure the filter**: Add the three parameters to your grid configuration:
   ```yaml
   country_polygon_path: "path/to/countries.shp"
   country_filter_column: "NAME"
   country_filter_value: "France"
   ```

4. **How it works**:
   - If bbox is not provided, it's automatically calculated from the country polygon
   - This ensures all islands and territories are included in the bbox
   - The program generates a grid covering the bounding box
   - Each point is checked if it's within the country polygon
   - Only points inside the country boundary are kept and processed
   - This ensures you only get images for areas within the country

**Benefits**:
- Avoids generating points in ocean/neighboring countries
- More efficient: fewer points to process
- Accurate coverage: only areas of interest
- **Automatic bbox calculation**: When using country polygon, bbox is automatically calculated from the polygon
- **Includes all territories**: Ensures islands and overseas territories are included in the bbox
- **No manual bbox needed**: You don't need to guess or manually calculate the bbox

**Note**: When using country polygon filtering, the bbox is automatically calculated from the polygon's bounds. This ensures all parts of the country (including islands and territories) are covered. If you provide a bbox manually, it will be overridden by the polygon's bbox to ensure complete coverage.

## Tips

1. **Start small**: Test with a small bbox and large spacing first
2. **Check spacing**: Make sure spacing is appropriate for your use case
   - Too small: many points, long processing time
   - Too large: may miss areas of interest
3. **Use incremental for large grids**: For grids with many points, use `incremental: true`
4. **Coordinate system**: All coordinates are in WGS84 (EPSG:4326) - degrees
5. **Country filtering**: Use country polygon filtering to avoid generating points outside your area of interest
6. **Check shapefile columns**: Inspect your country shapefile to find the correct column name for filtering

## Calculation Reference

- 1 degree of longitude ≈ 111 km at equator (varies by latitude)
- 1 degree of latitude ≈ 111 km (constant)
- At 45° latitude: 1 degree longitude ≈ 78.5 km

For a bbox of `[minx, miny, maxx, maxy]`:
- Width: `(maxx - minx) * 111` km (approximate)
- Height: `(maxy - miny) * 111` km
- Number of points: `ceil((maxx - minx) / spacing) * ceil((maxy - miny) / spacing)`

