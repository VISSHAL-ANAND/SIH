import numpy as np

from main.geolocation import extract_geotiff_coords


def test_geotiff_coordinates_use_pixel_center(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    path = tmp_path / "center_test.tif"
    transform = from_origin(80.0, 13.0, 0.0001, 0.0001)
    data = np.zeros((10, 10), dtype=np.uint8)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    lat, lon = extract_geotiff_coords(path, 0, 0)
    assert abs(lat - 12.99995) < 1e-6
    assert abs(lon - 80.00005) < 1e-6

    lat, lon = extract_geotiff_coords(path, 9, 9)
    assert abs(lat - 12.99905) < 1e-6
    assert abs(lon - 80.00095) < 1e-6
