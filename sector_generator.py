import geopandas as gpd
from shapely.geometry import box, Point
import matplotlib.pyplot as plt


def generate(governorate="الغربية", long_step=0.1, lat_step=0.05):
    # Load the GeoJSON file
    gdf = gpd.read_file("gadm41_EGY_1.json")

    # Choose the governorate
    gov_name = f"محافظة{governorate}"
    gov_shape = gdf[gdf["NL_NAME_1"] == gov_name]

    # Get bounding box
    minx, miny, maxx, maxy = gov_shape.total_bounds

    # Step sizes
    center_points = []
    grid_cells = []

    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, x + long_step, y + lat_step)
            if cell.intersects(gov_shape.unary_union):
                centroid = cell.centroid
                center_points.append(
                    (round(centroid.y, 6), round(centroid.x, 6))
                )  # (lat, lon)
                grid_cells.append(cell)
            y += lat_step
        x += long_step

    # print(len(center_points))
    # print(center_points)

    return center_points


generate()

if __name__ == "__main__":
    generate()
# grid_gdf = gpd.GeoDataFrame(geometry=grid_cells, crs=gdf.crs)
# center_gdf = gpd.GeoDataFrame(
#     geometry=[Point(lon, lat) for lat, lon in center_points], crs=gdf.crs
# )

# # Plot everything
# fig, ax = plt.subplots(figsize=(10, 10))
# gov_shape.plot(ax=ax, color="lightblue", edgecolor="black")
# grid_gdf.boundary.plot(ax=ax, color="red", linewidth=0.8)
# center_gdf.plot(ax=ax, color="black", markersize=10)

# # Optional: Label center points
# for i, point in enumerate(center_gdf.geometry):
#     ax.annotate(
#         str(i + 1),
#         xy=(point.x, point.y),
#         xytext=(3, 3),
#         textcoords="offset points",
#         fontsize=8,
#     )

# plt.title(f"{gov_name} — Sector Centers (Lat Step: 0.07°, Lon Step: 0.1°)")
# plt.xlabel("Longitude")
# plt.ylabel("Latitude")
# plt.grid(True)
# plt.show()

# # Optional: print centers
# print(f"Total center points in {gov_name}: {len(center_points)}\n")
# for idx, (lat, lon) in enumerate(center_points, 1):
#     print(f"{idx}. Latitude: {lat}, Longitude: {lon}")
