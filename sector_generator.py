import geopandas as gpd
from shapely.geometry import box, Point
import matplotlib.pyplot as plt


def generate(governorate="بنى سويف", long_step=0.1, lat_step=0.05):
    # Load the GeoJSON file
    gdf = gpd.read_file("gadm41_EGY_1.json")

    # remove spaces between governorate name
    governorate = governorate.replace(" ", "")
    # Choose the governorate
    gov_name = f"محافظة{governorate}"
    gov_shape = gdf[gdf["NL_NAME_1"] == gov_name]

    if gov_shape.empty:
        print(f"[❌] Governorate '{gov_name}' not found in GeoJSON file!")
        print("[ℹ️] Available names:", gdf["NL_NAME_1"].unique())
        return

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
                # if (30.69 <= centroid.x <= 31.25) and (
                #     28.6726 <= centroid.y <= 29.5026
                # ):
                center_points.append(
                    (round(centroid.y, 6), round(centroid.x, 6))
                )  # (lat, lon)
                grid_cells.append(cell)
            y += lat_step
        x += long_step

    print(len(center_points))
    print(center_points)

    # return center_points

    grid_gdf = gpd.GeoDataFrame(geometry=grid_cells, crs=gdf.crs)
    center_gdf = gpd.GeoDataFrame(
        geometry=[Point(lon, lat) for lat, lon in center_points], crs=gdf.crs
    )

    # Plot everything
    fig, ax = plt.subplots(figsize=(10, 10))
    gov_shape.plot(ax=ax, color="lightblue", edgecolor="black")
    grid_gdf.boundary.plot(ax=ax, color="red", linewidth=0.8)
    center_gdf.plot(ax=ax, color="black", markersize=10)

    # Optional: Label center points
    for i, point in enumerate(center_gdf.geometry):
        ax.annotate(
            str(i + 1),
            xy=(point.x, point.y),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=8,
        )

    plt.title(f"{gov_name} — Sector Centers (Lat Step: 0.07°, Lon Step: 0.1°)")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.grid(True)
    plt.show()

    # Optional: print centers
    print(f"Total center points in {gov_name}: {len(center_points)}\n")
    for idx, (lat, lon) in enumerate(center_points, 1):
        print(f"{idx}. Latitude: {lat}, Longitude: {lon}")


generate()

# import json

# coordinates = [  # نسخ بياناتك هنا
#     [
#         [31.785, 28.7422],
#         [31.7661, 28.6916],
#         [31.784, 28.6313],
#         [31.7562, 28.5638],
#         [31.8857, 28.2993],
#         [31.7122, 28.2476],
#         [31.5554, 28.2665],
#         [31.3572, 28.3296],
#         [31.2266, 28.4001],
#         [31.1652, 28.4913],
#         [31.1082, 28.6085],
#         [31.0325, 28.6987],
#         [30.9013, 28.7093],
#         [30.9012, 28.7081],
#         [30.8874, 28.7084],
#         [30.8844, 28.7198],
#         [30.8617, 28.7172],
#         [30.8425, 28.731],
#         [30.834, 28.7487],
#         [30.8124, 28.7458],
#         [30.8119, 28.7619],
#         [30.7964, 28.7563],
#         [30.7937, 28.7452],
#         [30.7789, 28.7624],
#         [30.7374, 28.7678],
#         [29.7733, 28.779],
#         [29.8565, 29.0913],
#         [30.1099, 29.0395],
#         [30.2948, 29.0272],
#         [30.2983, 28.9676],
#         [30.378, 28.9635],
#         [30.5062, 28.9921],
#         [30.8167, 29.0828],
#         [30.8696, 29.1313],
#         [30.9053, 29.2053],
#         [30.9501, 29.2059],
#         [30.9719, 29.1971],
#         [30.9825, 29.2174],
#         [31.0042, 29.2158],
#         [30.9948, 29.2378],
#         [30.9945, 29.2414],
#         [31.0138, 29.2572],
#         [31.0679, 29.3492],
#         [31.1262, 29.4218],
#         [31.1785, 29.4321],
#         [31.2017, 29.4019],
#         [31.2282, 29.3997],
#         [31.234, 29.378],
#         [31.2139, 29.3449],
#         [31.2213, 29.2593],
#         [31.213, 29.2461],
#         [31.2135, 29.2201],
#         [31.2022, 29.2027],
#         [31.2073, 29.1965],
#         [31.4674, 29.0907],
#         [31.8346, 28.9937],
#         [31.8746, 28.907],
#         [31.7959, 28.7714],
#         [31.785, 28.7422],
#     ]
# ]

# filtered_coords = [[lon, lat] for lon, lat in coordinates[0] if 30.96 <= lon <= 31.25]

# print(json.dumps(filtered_coords, indent=4))
