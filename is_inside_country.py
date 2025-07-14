import os

import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import nearest_points, unary_union
from logger import country_logger


# Mapping of Egypt governorates from Arabic to English
EGYPT_GOVERNORATE_AR_EN = {
    "القاهرة": "Cairo",
    "الجيزة": "Giza",
    "الإسكندرية": "Alexandria",
    "الدقهلية": "Dakahlia",
    "البحر الأحمر": "Red Sea",
    "البحيرة": "Beheira",
    "الفيوم": "Faiyum",
    "الغربية": "Gharbia",
    "الإسماعيلية": "Ismailia",
    "المنوفية": "Monufia",
    "المنيا": "Minya",
    "القليوبية": "Qalyubia",
    "الوادي الجديد": "New Valley",
    "السويس": "Suez",
    "أسوان": "Aswan",
    "أسيوط": "Asyut",
    "بني سويف": "Beni Suef",
    "بورسعيد": "Port Said",
    "دمياط": "Damietta",
    "الشرقية": "Sharqia",
    "جنوب سيناء": "South Sinai",
    "كفر الشيخ": "Kafr El Sheikh",
    "مطروح": "Matrouh",
    "الأقصر": "Luxor",
    "قنا": "Qena",
    "شمال سيناء": "North Sinai",
    "سوهاج": "Sohag",
    "حلوان": "Helwan",
    "6 أكتوبر": "6th of October",
    "الأقصر": "Luxor",
    "مرسى مطروح": "Marsa Matrouh",
}

# Cache for loaded country boundaries
_country_boundary_cache = {}


def find_location(lat, long, country):
    if not (-90 <= lat <= 90):
        raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90.")
    if not (-180 <= long <= 180):
        raise ValueError(f"Invalid longitude: {long}. Must be between -180 and 180.")

    # Check if shapefile exists
    if country == "Egypt":
        shapefile_path = "gadm41_EGY_shp/gadm41_EGY_0.shp"
    elif country == "Saudi Arabia":
        shapefile_path = "gadm41_SAU_shp/gadm41_SAU_0.shp"
    else:
        raise ValueError(f"Unsupported country: {country}")

    if not os.path.exists(shapefile_path):
        country_logger.error(f"Shapefile not found at {shapefile_path}")
        raise FileNotFoundError(f"Shapefile not found at {shapefile_path}")

    # Load country's boundary from cache or disk
    if country not in _country_boundary_cache:
        try:
            _country_boundary_cache[country] = gpd.read_file(shapefile_path)
        except Exception as e:
            country_logger.error(f"Failed to load shapefile: {e}")
            raise RuntimeError(f"Failed to load shapefile: {e}")

    country_boundary = _country_boundary_cache[country]

    # Create a point with longitude, latitude
    point = Point(long, lat)

    # Check if the point is within the country's boundary
    is_within_country = country_boundary.contains(point).any()

    return is_within_country, country_boundary, point


def find_near_location(lat, long, country):
    inside, country_boundary, point = find_location(lat, long, country)

    if inside:
        return (True, lat, long)
    else:
        try:
            boundary = country_boundary.boundary
            if boundary.empty:
                # If boundary is empty, use the geometry itself
                boundary = country_boundary.geometry

            country_boundary_union = unary_union(boundary)

            if country_boundary_union.is_empty:
                # If we still have an empty geometry, return the original point
                return (False, lat, long)

            # Find the nearest point on the boundary
            nearest = nearest_points(point, country_boundary_union)[1]

            # Extract latitude and longitude from the nearest point
            nearest_long, nearest_lat = nearest.x, nearest.y
            return (False, nearest_lat, nearest_long)

        except Exception as e:
            # If anything goes wrong, log the error and return the original point
            country_logger.error(f"Error finding nearest point: {e}")
            return (False, lat, long)
