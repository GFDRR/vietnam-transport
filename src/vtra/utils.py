"""Shared plotting functions
"""
import configparser
import csv
import glob
import json
import os
from collections import OrderedDict, namedtuple
from math import floor, log10

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import Voronoi

import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
import fiona
import fiona.crs
import geopandas as gpd
import rasterio
import shapely.geometry
import shapely.ops
from boltons.iterutils import pairwise
from colour import Color
from geopy.distance import vincenty
from osgeo import gdal
from shapely.geometry import Polygon, shape


def load_config():
    """Read config.json
    """
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
    with open(config_path, 'r') as config_fh:
        config = json.load(config_fh)
    return config


def get_axes(extent=None, figsize=None, epsg=None):
    """Get transverse mercator axes (default to Vietnam extent)
    EPSG:4756
    """
    if extent is None:
        # extent = [102.2, 109.5, 8.5, 23.3]  # mainland extent
        extent = [101.8, 118.3, 6.7, 23.6]  # include islands
    if figsize is None:
        # figsize = (6, 10)  # mainland (portrait)
        figsize = (12, 10)  # include islands

    if epsg is not None:
        ax_proj = ccrs.epsg(epsg)
    else:
        x0, x1, y0, y1 = extent
        cx = x0 + ((x1 - x0) / 2)
        cy = y0 + ((y1 - y0) / 2)
        ax_proj = ccrs.LambertConformal(central_longitude=cx, central_latitude=cy)

    plt.figure(figsize=figsize, dpi=300)
    ax = plt.axes([0.025, 0.025, 0.95, 0.95], projection=ax_proj)
    proj = ccrs.PlateCarree()
    ax.set_extent(extent, crs=proj)
    set_ax_bg(ax)
    return ax


def save_fig(output_filename):
    plt.savefig(output_filename)


def set_ax_bg(ax, color='#c6e0ff'):
    """Set axis background color
    """
    ax.background_patch.set_facecolor(color)


def plot_basemap(ax, data_path, focus='VNM', neighbours=None,
                 country_border='white', plot_regions=True, plot_states=True,
                 plot_districts=False, highlight_region=None):
    """Plot countries and regions background
    """
    proj = ccrs.PlateCarree()

    if neighbours is None:
        neighbours = ['VNM', 'CHN', 'LAO', 'KHM', 'THA', 'PHL', 'MYS', 'BRN']

    states_filename = os.path.join(
        data_path,
        'Global_boundaries',
        'Natural_Earth',
        'ne_10m_admin_0_countries_lakes.shp'
    )

    states_over_lakes_filename = os.path.join(
        data_path,
        'Global_boundaries',
        'Natural_Earth',
        'ne_10m_admin_0_countries.shp'
    )

    provinces_filename = os.path.join(
        data_path,
        'Vietnam_boundaries',
        'who_boundaries',
        'who_provinces.shp'
    )

    districts_filename = os.path.join(
        data_path,
        'Vietnam_boundaries',
        'who_boundaries',
        'who_districts.shp'
    )

    lakes_filename = os.path.join(
        data_path,
        'Global_boundaries',
        'Natural_Earth',
        'ne_10m_lakes.shp'
    )

    # Neighbours
    if plot_states:
        for record in shpreader.Reader(states_filename).records():
            country_code = record.attributes['ISO_A3']
            if country_code in neighbours:
                geom = record.geometry
                ax.add_geometries(
                    [geom],
                    crs=proj,
                    edgecolor=country_border,
                    facecolor='#e0e0e0',
                    linewidth=0.5,
                    zorder=1)

    # Regions
    if highlight_region is None:
        highlight_region = []
    highlight_region_geom = None
    if highlight_region is None:
        highlight_region = []
    if plot_regions:
        for record in shpreader.Reader(provinces_filename).records():
            if record.attributes['NAME_ENG'] in highlight_region:
                ax.add_geometries([record.geometry], crs=proj,
                                  edgecolor='#ffffff', facecolor='#7c7c7c', linewidth=0.5)
                highlight_region_geom = record.geometry
            else:
                ax.add_geometries([record.geometry], crs=proj,
                                  edgecolor='#ffffff', facecolor='#d2d2d2', linewidth=0.5)

    # Districts
    if plot_districts:
        for record in shpreader.Reader(districts_filename).records():
            if highlight_region and highlight_region_geom:
                district_region = record.attributes['name_prov']
                if district_region == highlight_region or \
                        shape(record.geometry.centroid).intersects(highlight_region_geom):
                    ax.add_geometries([record.geometry], crs=proj, edgecolor='#ffffff',
                                      facecolor='#c7c7c7', linewidth=0.5)

            else:
                ax.add_geometries([record.geometry], crs=proj, edgecolor='#ffffff',
                                  facecolor='#d2d2d2', linewidth=0.5)

    # Lakes
    for record in shpreader.Reader(lakes_filename).records():
        name = record.attributes['name']
        geom = record.geometry
        ax.add_geometries(
            [geom],
            crs=proj,
            edgecolor='none',
            facecolor='#c6e0ff',
            zorder=1)


def plot_basemap_labels_large_region(ax, data_path):

    labels = [
        ('Vietnam', 108.633, 13.625, 9),
        ('Myanmar', 97.383, 21.535, 9),
        ('Malaysia', 99.404, 8.624, 9),
        ('Indonesia', 97.822, 3.338, 9),
        ('Singapore', 103.799, 1.472, 9),
        ('Cambodia', 105.25, 12.89, 9),
        ('Lao PDR', 105.64, 16.55, 9),
        ('Thailand', 101.360, 16.257, 9),
        ('China', 108.08, 22.71, 9)
    ]
    plot_basemap_labels(ax, data_path, labels, province_zoom=False, plot_regions=False)


def plot_district_labels(ax, data_path, highlight_region=None):
    provinces_filename = os.path.join(
        data_path,
        'Vietnam_boundaries',
        'who_boundaries',
        'who_provinces.shp'
    )
    districts_filename = os.path.join(
        data_path,
        'Vietnam_boundaries',
        'who_boundaries',
        'who_districts.shp'
    )

    highlight_region_geom = None
    if highlight_region:
        for record in shpreader.Reader(provinces_filename).records():
            if record.attributes['NAME_ENG'] in highlight_region:
                highlight_region_geom = record.geometry

    district_labels = []
    for record in shpreader.Reader(districts_filename).records():
        if highlight_region:
            district_region = record.attributes['name_prov']
            if district_region == highlight_region:
                district_labels.append(get_district_label(record))
            elif highlight_region_geom and \
                    shape(record.geometry.centroid).intersects(highlight_region_geom):
                district_labels.append(get_district_label(record))
        else:
            district_labels.append(get_district_label(record))
    plot_basemap_labels(ax, None, district_labels)


def get_district_label(record):
    district_name = record.attributes['NAME_ENG']
    centroid = shape(record.geometry).centroid
    return (district_name, centroid.x, centroid.y, 9)


def plot_basemap_labels(ax, data_path, labels=None, province_zoom=False, plot_regions=True, plot_international_left=True,plot_international_right=True):
    """Plot countries and regions background
    """
    proj = ccrs.PlateCarree()
    extent = ax.get_extent(crs=proj)

    if labels is None:
        labels = []

        if plot_international_left:
            labels = labels + [
                ('Cambodia', 105.25, 12.89, 9),
                ('Lao PDR', 105.64, 16.55, 9),
                ('Thailand', 103.64, 15.25, 9)]

        if plot_international_right:
            labels = labels + [
                ('China', 108.08, 22.71, 9)
                ]

        if plot_regions:
            labels = labels + [
                # Provinces
                ('An Giang', 105.182, 10.491, 5),
                ('Ba Ria-Vung Tau', 107.250, 10.510, 5),
                ('Bac Giang', 106.480, 21.357, 5),
                ('Bac Kan', 105.826, 22.261, 5),
                ('Bac Lieu', 105.489, 9.313, 5),
                ('Bac Ninh', 106.106, 21.109, 5),
                ('Ben Tre', 106.469, 10.118, 5),
                ('Binh Dinh', 108.951, 14.121, 5),
                ('Binh Duong', 106.658, 11.216, 5),
                ('Binh Phuoc', 106.907, 11.754, 5),
                ('Binh Thuan', 108.048, 11.117, 5),
                ('Ca Mau', 105.036, 9.046, 5),
                ('Can Tho', 105.530, 10.184, 5),
                ('Cao Bang', 106.087, 22.744, 5),
                ('Da Nang', 108.234, 16.057, 5),
                ('Dak Lak', 108.212, 12.823, 5),
                ('Dak Nong', 107.688, 12.228, 5),
                ('Dien Bien', 103.022, 21.710, 5),
                ('Dong Nai', 107.185, 11.058, 5),
                ('Dong Thap', 105.608, 10.564, 5),
                ('Gia Lai', 108.241, 13.797, 5),
                ('Ha Giang', 104.979, 22.767, 5),
                ('Ha Nam', 105.966, 20.540, 5),
                ('Ha Noi', 105.700, 20.998, 5),
                ('Ha Tinh', 105.737, 18.290, 5),
                ('Hai Duong', 106.361, 20.930, 5),
                ('Hai Phong', 106.686, 20.798, 5),
                ('Hau Giang', 105.624, 9.784, 5),
                ('Ho Chi Minh', 106.697, 10.743, 5),
                ('Hoa Binh', 105.343, 20.684, 5),
                ('Hung Yen', 106.060, 20.814, 5),
                ('Khanh Hoa', 109.172, 12.271, 5),
                ('Kien Giang', 104.942, 9.998, 5),
                ('Kon Tum', 107.875, 14.647, 5),
                ('Lai Chau', 103.187, 22.316, 5),
                ('Lam Dong', 108.095, 11.750, 5),
                ('Lang Son', 106.621, 21.838, 5),
                ('Lao Cai', 104.112, 22.365, 5),
                ('Long An', 106.171, 10.730, 5),
                ('Nam Dinh', 106.217, 20.268, 5),
                ('Nghe An', 104.944, 19.236, 5),
                ('Ninh Binh', 105.903, 20.170, 5),
                ('Ninh Thuan', 108.869, 11.705, 5),
                ('Phu Tho', 105.116, 21.308, 5),
                ('Phu Yen', 109.059, 13.171, 5),
                ('Quang Binh', 106.293, 17.532, 5),
                ('Quang Nam', 107.960, 15.589, 5),
                ('Quang Ngai', 108.650, 14.991, 5),
                ('Quang Ninh', 107.278, 21.245, 5),
                ('Quang Tri', 106.929, 16.745, 5),
                ('Soc Trang', 105.928, 9.558, 5),
                ('Son La', 104.070, 21.192, 5),
                ('Tay Ninh', 106.161, 11.404, 5),
                ('Thai Binh', 106.419, 20.450, 5),
                ('Thai Nguyen', 105.823, 21.692, 5),
                ('Thanh Hoa', 105.319, 20.045, 5),
                ('Thua Thien Hue', 107.512, 16.331, 5),
                ('Tien Giang', 106.309, 10.396, 5),
                ('Tra Vinh', 106.318, 9.794, 5),
                ('Tuyen Quang', 105.267, 22.113, 5),
                ('Vinh Long', 105.991, 10.121, 5),
                ('Vinh Phuc', 105.559, 21.371, 5),
                ('Yen Bai', 104.568, 21.776, 5),
            ]

    for text, x, y, size in labels:

        if province_zoom == True:
            size = 18

        if within_extent(x, y, extent):
            ax.text(
                x, y,
                text,
                alpha=0.7,
                size=size,
                horizontalalignment='center',
                zorder=10,
                transform=proj)


def get_region_plot_settings(region):
    """Common definition of region plot settings
    """
    region_plot_settings_lut = [
        {
            'name': 'Binh Dinh',
            'bbox': (108.5, 109.4, 14.75, 13.5),
            'weight_legend': {
                'x_l': 108.53,
                'x_r': 108.58,
                'base_y': 13.84,
                'y_step': 0.035,
                'y_text_nudge': 0.01,
                'x_text_nudge': 0.04
            },
            'scale_legend': 10,
            'figure_size': (7, 10)
        },
        {
            'name': 'Lao Cai',
            'bbox': (103.5, 104.7, 22.9, 21.8),
            'weight_legend': {
                'x_l': 103.53,
                'x_r': 103.58,
                'base_y': 22.18,
                'y_step': 0.04,
                'y_text_nudge': 0.01,
                'x_text_nudge': 0.04
            },
            'scale_legend': 10,
            'figure_size': (10, 10)
        },
        {
            'name': 'Thanh Hoa',
            'bbox': (104.35, 106.1, 20.7, 19.1),
            'weight_legend': {
                'x_l': 104.4,
                'x_r': 104.47,
                'base_y': 19.68,
                'y_step': 0.06,
                'y_text_nudge': 0.01,
                'x_text_nudge': 0.04
            },
            'scale_legend': 10,
            'figure_size': (10, 10)
        }
    ]

    for region_plot_settings in region_plot_settings_lut:
        if region == region_plot_settings['name']:
            return region_plot_settings

    raise Exception('Region plot settings not defined for this region')


def within_extent(x, y, extent):
    xmin, xmax, ymin, ymax = extent
    return (xmin < x) and (x < xmax) and (ymin < y) and (y < ymax)


def scale_bar(ax, length=100, location=(0.5, 0.05), linewidth=3):
    """Draw a scale bar

    Adapted from https://stackoverflow.com/questions/32333870/how-can-i-show-a-km-ruler-on-a-cartopy-matplotlib-plot/35705477#35705477

    Parameters
    ----------
    ax : axes
    length : int
        length of the scalebar in km.
    location: tuple
        center of the scalebar in axis coordinates (ie. 0.5 is the middle of the plot)
    linewidth: float
        thickness of the scalebar.
    """
    # lat-lon limits
    llx0, llx1, lly0, lly1 = ax.get_extent(ccrs.PlateCarree())

    # Transverse mercator for length
    x = (llx1 + llx0) / 2
    y = lly0 + (lly1 - lly0) * location[1]
    tmc = ccrs.TransverseMercator(x, y)

    # Extent of the plotted area in coordinates in metres
    x0, x1, y0, y1 = ax.get_extent(tmc)

    # Scalebar location coordinates in metres
    sbx = x0 + (x1 - x0) * location[0]
    sby = y0 + (y1 - y0) * location[1]
    bar_xs = [sbx - length * 500, sbx + length * 500]

    # Plot the scalebar and label
    ax.plot(bar_xs, [sby, sby], transform=tmc, color='k', linewidth=linewidth)
    ax.text(sbx, sby + 10*length, str(length) + ' km', transform=tmc,
            horizontalalignment='center', verticalalignment='bottom', size=8)


def generate_weight_bins(weights, n_steps=9, width_step=0.01):
    """Given a list of weight values, generate <n_steps> bins with a width
    value to use for plotting e.g. weighted network flow maps.
    """
    min_weight = min(weights)
    max_weight = max(weights)

    width_by_range = OrderedDict()

    mins = np.linspace(min_weight, max_weight, n_steps)
    maxs = list(mins)
    maxs.append(max_weight*10)
    maxs = maxs[1:]

    assert len(maxs) == len(mins)

    for i, (min_, max_) in enumerate(zip(mins, maxs)):
        width_by_range[(min_, max_)] = (i+1) * width_step

    return width_by_range


def generate_weight_bins_with_colour_gradient(weights, n_steps=9, width_step=0.01, colours=['orange', 'red']):
    """Given a list of weight values, generate <n_steps> bins with a width
    value to use for plotting e.g. weighted network flow maps.
    """
    min_weight = min(weights)
    max_weight = max(weights)

    width_by_range = OrderedDict()

    mins = np.linspace(min_weight, max_weight, n_steps)
    maxs = list(mins)
    maxs.append(max_weight*10)
    maxs = maxs[1:]

    assert len(maxs) == len(mins)

    low_color = Color(colours[0])
    high_color = Color(colours[1])
    colors = list(low_color.range_to(high_color, n_steps))

    for i, (min_, max_) in enumerate(zip(mins, maxs)):
        width_by_range[(min_, max_)] = (i, (i+1) * width_step, colors[i])

    return width_by_range


Style = namedtuple('Style', ['color', 'zindex', 'label'])
Style.__doc__ += """: class to hold an element's styles

Used to generate legend entries, apply uniform style to groups of map elements
(See network_map.py for example.)
"""


def legend_from_style_spec(ax, styles, loc='lower left'):
    """Plot legend
    """
    handles = [
        mpatches.Patch(color=style.color, label=style.label)
        for style in styles.values()
    ]
    ax.legend(
        handles=handles,
        loc=loc
    )


def round_sf(x, places=1):
    """Round number to significant figures
    """
    if x == 0:
        return 0
    sign = x / abs(x)
    x = abs(x)
    exp = floor(log10(x)) + 1
    shift = 10 ** (exp - places)
    rounded = round(x / shift) * shift
    return rounded * sign


def get_data(filename):
    """Read in data (as array) and extent of each raster
    """
    gdal.UseExceptions()
    ds = gdal.Open(filename)
    data = ds.ReadAsArray()
    data[data < 0] = 0

    gt = ds.GetGeoTransform()

    # get the edge coordinates
    width = ds.RasterXSize
    height = ds.RasterYSize
    xres = gt[1]
    yres = gt[5]

    xmin = gt[0]
    xmax = gt[0] + (xres * width)
    ymin = gt[3] + (yres * height)
    ymax = gt[3]

    lat_lon_extent = (xmin, xmax, ymax, ymin)

    return data, lat_lon_extent


def line_length(line, ellipsoid='WGS-84'):
    """Length of a line in meters, given in geographic coordinates.

    Adapted from https://gis.stackexchange.com/questions/4022/looking-for-a-pythonic-way-to-calculate-the-length-of-a-wkt-linestring#answer-115285

    Args:
        line: a shapely LineString object with WGS-84 coordinates.

        ellipsoid: string name of an ellipsoid that `geopy` understands (see http://geopy.readthedocs.io/en/latest/#module-geopy.distance).

    Returns:
        Length of line in kilometers.
    """
    if line.geometryType() == 'MultiLineString':
        return sum(line_length(segment) for segment in line)

    return sum(
        vincenty(tuple(reversed(a)), tuple(reversed(b)), ellipsoid=ellipsoid).kilometers
        for a, b in pairwise(line.coords)
    )


def gdf_geom_clip(gdf_in, clip_geom):
    """Filter a dataframe to contain only features within a clipping geometry

    Parameters
    ---------
    gdf_in
        geopandas dataframe to be clipped in
    province_geom
        shapely geometry of province for what we do the calculation

    Returns
    -------
    filtered dataframe
    """
    return gdf_in.loc[gdf_in['geometry'].apply(lambda x: x.within(clip_geom))].reset_index(drop=True)


def gdf_clip(shape_in, clip_geom):
    """Filter a file to contain only features within a clipping geometry

    Parameters
    ----------
    shape_in
        path string to shapefile to be clipped
    province_geom
        shapely geometry of province for what we do the calculation

    Returns
    -------
    filtered dataframe
    """
    gdf = gpd.read_file(shape_in)
    gdf = gdf.to_crs({'init': 'epsg:4326'})
    return gdf.loc[gdf['geometry'].apply(lambda x: x.within(clip_geom))].reset_index(drop=True)


def get_nearest_node(x, sindex_input_nodes, input_nodes, id_column):
    """Get nearest node in a dataframe

    Parameters
    ----------
    x
        row of dataframe
    sindex_nodes
        spatial index of dataframe of nodes in the network
    nodes
        dataframe of nodes in the network
    id_column
        name of column of id of closest node

    Returns
    -------
    Nearest node to geometry of row
    """
    return input_nodes.loc[list(sindex_input_nodes.nearest(x.bounds[:2]))][id_column].values[0]


def get_nearest_node_within_region(x, input_nodes, id_column, region_id):
    select_nodes = input_nodes.loc[input_nodes[region_id] == x[region_id]]
    # print (input_nodes)
    if len(select_nodes.index) > 0:
        select_nodes = select_nodes.reset_index()
        sindex_input_nodes = select_nodes.sindex
        return select_nodes.loc[list(sindex_input_nodes.nearest(x.geometry.bounds[:2]))][id_column].values[0]
    else:
        return ''


def count_points_in_polygon(x, points_sindex):
    """Count points in a polygon

    Parameters
    ----------
    x
        row of dataframe
    points_sindex
        spatial index of dataframe with points in the region to consider

    Returns
    -------
    Number of points in polygon
    """
    return len(list(points_sindex.intersection(x.bounds)))


def extract_value_from_gdf(x, gdf_sindex, gdf, column_name):
    """Access value

    Parameters
    ----------
    x
        row of dataframe
    gdf_sindex
        spatial index of dataframe of which we want to extract the value
    gdf
        GeoDataFrame of which we want to extract the value
    column_name
        column that contains the value we want to extract

    Returns
    -------
    extracted value from other gdf
    """
    return gdf.loc[list(gdf_sindex.intersection(x.bounds[:2]))][column_name].values[0]


def assign_value_in_area_proportions(poly_1_gpd, poly_2_gpd, poly_attribute):
    poly_1_sindex = poly_1_gpd.sindex
    for p_2_index, polys_2 in poly_2_gpd.iterrows():
        poly2_attr = 0
        intersected_polys = poly_1_gpd.iloc[list(
            poly_1_sindex.intersection(polys_2.geometry.bounds))]
        for p_1_index, polys_1 in intersected_polys.iterrows():
            if (polys_2['geometry'].intersects(polys_1['geometry']) is True) and (polys_1.geometry.is_valid is True) and (polys_2.geometry.is_valid is True):
                poly2_attr += polys_1[poly_attribute]*polys_2['geometry'].intersection(
                    polys_1['geometry']).area/polys_1['geometry'].area

        poly_2_gpd.loc[p_2_index, poly_attribute] = poly2_attr

    return poly_2_gpd


def assign_value_in_area_proportions_within_common_region(poly_1_gpd, poly_2_gpd, poly_attribute, common_region_id):
    poly_1_sindex = poly_1_gpd.sindex
    for p_2_index, polys_2 in poly_2_gpd.iterrows():
        poly2_attr = 0
        poly2_id = polys_2[common_region_id]
        intersected_polys = poly_1_gpd.iloc[list(
            poly_1_sindex.intersection(polys_2.geometry.bounds))]
        for p_1_index, polys_1 in intersected_polys.iterrows():
            if (polys_1[common_region_id] == poly2_id) and (polys_2['geometry'].intersects(polys_1['geometry']) is True) and (polys_1.geometry.is_valid is True) and (polys_2.geometry.is_valid is True):
                poly2_attr += polys_1[poly_attribute]*polys_2['geometry'].intersection(
                    polys_1['geometry']).area/polys_1['geometry'].area

        poly_2_gpd.loc[p_2_index, poly_attribute] = poly2_attr

    return poly_2_gpd


def voronoi_finite_polygons_2d(vor, radius=None):
    """Reconstruct infinite voronoi regions in a 2D diagram to finite regions.

    Source: https://stackoverflow.com/questions/36063533/clipping-a-voronoi-diagram-python

    Parameters
    ----------
    vor : Voronoi
        Input diagram
    radius : float, optional
        Distance to 'points at infinity'

    Returns
    -------
    regions : list of tuples
        Indices of vertices in each revised Voronoi regions.
    vertices : list of tuples
        Coordinates for revised Voronoi vertices. Same as coordinates
        of input vertices, with 'points at infinity' appended to the
        end
    """

    if vor.points.shape[1] != 2:
        raise ValueError("Requires 2D input")

    new_regions = []
    new_vertices = vor.vertices.tolist()

    center = vor.points.mean(axis=0)
    if radius is None:
        radius = vor.points.ptp().max()*2

    # Construct a map containing all ridges for a given point
    all_ridges = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    # Reconstruct infinite regions
    for p1, region in enumerate(vor.point_region):
        vertices = vor.regions[region]

        if all(v >= 0 for v in vertices):
            # finite region
            new_regions.append(vertices)
            continue

        # reconstruct a non-finite region
        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]

        for p2, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                # finite ridge: already in the region
                continue

            # Compute the missing endpoint of an infinite ridge

            t = vor.points[p2] - vor.points[p1]  # tangent
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])  # normal

            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far_point = vor.vertices[v2] + direction * radius

            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())

        # sort region counterclockwise
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = np.array(new_region)[np.argsort(angles)]

        # finish
        new_regions.append(new_region.tolist())

    return new_regions, np.asarray(new_vertices)


def extract_nodes_within_gdf(x, input_nodes, column_name):
    return input_nodes.loc[list(input_nodes.geometry.within(x.geometry))][column_name].values[0]


def extract_gdf_values_containing_nodes(x, sindex_input_gdf, input_gdf, column_name):
    a = input_gdf.loc[list(input_gdf.geometry.contains(x.geometry))]
    if len(a.index) > 0:
        return input_gdf.loc[list(input_gdf.geometry.contains(x.geometry))][column_name].values[0]
    else:
        return get_nearest_node(x.geometry, sindex_input_gdf, input_gdf, column_name)

def get_node_edge_files_in_path(mode_file_path):
    """Get the paths of edge and node files in folder

    Parameters
    ----------
    mode_file_path : Path of mode file

    Returns
    -------
    edges_in : Path of edges shapefile
    nodes_in: Path of nodes shapefile

    Error Exception
    ---------------
    Prints error if node or edge file missing

    """
    for file in os.listdir(mode_file_path):
        try:
            if file.endswith('.shp') and 'edges' in file.lower().strip():
                edges_in = os.path.join(mode_file_path, file)
            if file.endswith('.shp') and 'nodes' in file.lower().strip():
                nodes_in = os.path.join(mode_file_path, file)
        except:
            print('Network nodes and edge files necessary')

    return nodes_in,edges_in

def get_node_edge_files(mode_file_path,file_identification):
    """Get the paths of edge and node files in folder

    Parameters
    ----------
    mode_file_path : str
        path of mode file
    file_identification : str
        name of file

    Returns
    -------
    edges_in
        Path of edges shapefile
    nodes_in
        Path of nodes shapefile

    Error Exception
    ---------------
    Prints error if node or edge file missing

    """
    for file in os.listdir(mode_file_path):
        try:
            if file.lower().strip() == '{}_edges.shp'.format(file_identification):
                edges_in = os.path.join(mode_file_path, file)
            if file.lower().strip() == '{}_nodes.shp'.format(file_identification):
                nodes_in = os.path.join(mode_file_path, file)
        except:
            print('Network nodes and edge files necessary')

    return nodes_in, edges_in
