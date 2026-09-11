"""Contract tests for Sentinel-1 SAFE annotation geolocation."""

from pathlib import Path

from main.geolocation import sentinel1_annotation_pixel_to_latlon


def test_sentinel1_geolocation_grid_interpolates(tmp_path: Path):
    xml = tmp_path / "annotation.xml"
    xml.write_text(
        """<root>
        <geolocationGridPointList>
          <geolocationGridPoint><line>0</line><pixel>0</pixel><latitude>20</latitude><longitude>92</longitude></geolocationGridPoint>
          <geolocationGridPoint><line>0</line><pixel>100</pixel><latitude>20</latitude><longitude>91</longitude></geolocationGridPoint>
          <geolocationGridPoint><line>100</line><pixel>0</pixel><latitude>19</latitude><longitude>92</longitude></geolocationGridPoint>
          <geolocationGridPoint><line>100</line><pixel>100</pixel><latitude>19</latitude><longitude>91</longitude></geolocationGridPoint>
        </geolocationGridPointList>
        </root>""",
        encoding="utf-8",
    )

    lat, lon = sentinel1_annotation_pixel_to_latlon(xml, 50, 50)
    assert abs(lat - 19.5) < 1e-9
    assert abs(lon - 91.5) < 1e-9


def test_sentinel1_geolocation_grid_edge_clamps(tmp_path: Path):
    xml = tmp_path / "annotation.xml"
    xml.write_text(
        """<root>
        <geolocationGridPointList>
          <geolocationGridPoint><line>0</line><pixel>0</pixel><latitude>20</latitude><longitude>92</longitude></geolocationGridPoint>
          <geolocationGridPoint><line>0</line><pixel>100</pixel><latitude>20</latitude><longitude>91</longitude></geolocationGridPoint>
          <geolocationGridPoint><line>100</line><pixel>0</pixel><latitude>19</latitude><longitude>92</longitude></geolocationGridPoint>
          <geolocationGridPoint><line>100</line><pixel>100</pixel><latitude>19</latitude><longitude>91</longitude></geolocationGridPoint>
        </geolocationGridPointList>
        </root>""",
        encoding="utf-8",
    )

    lat, lon = sentinel1_annotation_pixel_to_latlon(xml, -10, -10)
    assert lat == 20.0
    assert lon == 92.0
