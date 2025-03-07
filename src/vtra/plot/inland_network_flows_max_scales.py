"""Inland network flows map
"""
import os
import sys
from collections import OrderedDict

import pandas as pd
import geopandas as gpd
import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import LineString
from vtra.utils import *


def main():
    config = load_config()
    output_file = os.path.join(config['paths']['figures'], 'inland-map.png')
    inland_edge_file_path = os.path.join(
        config['paths']['data'], 'post_processed_networks', 'inland_edges.shp')
    inland_flow_file_path = os.path.join(config['paths']['output'], 'flow_mapping_combined',
                                   'weighted_flows_national_inland_100_percent.csv')
    inland_node_file = os.path.join(config['paths']['data'],
                                 'post_processed_networks', 'inland_nodes.shp')


    inland_edge_file = gpd.read_file(inland_edge_file_path,encoding='utf-8')
    inland_flow_file = pd.read_csv(inland_flow_file_path)
    inland_edge_file = pd.merge(inland_edge_file,inland_flow_file,how='left', on=['edge_id']).fillna(0)

    color = '#0689d7'
    color_by_type = {'Inland Line': color}

    crop_cols = ['max_rice', 'max_cash', 'max_cass', 'max_teas', 'max_maiz',
                 'max_rubb', 'max_swpo', 'max_acof', 'max_rcof', 'max_pepp']
    ind_cols = ['max_sugar', 'max_wood', 'max_steel', 'max_constructi', 'max_cement',
                'max_fertilizer', 'max_coal', 'max_petroluem', 'max_manufactur', 'max_fishery',
                'max_meat', 'max_tons']

    columns = crop_cols + ind_cols
    column_label_divisors = {c: 1000 for c in columns}

    legend_label = "AADF ('000 tons/day)"
    title_cols = ['Rice', 'Cashew', 'Cassava', 'Teas', 'Maize', 'Rubber',
                'Sweet Potatoes', 'Coffee Arabica', 'Coffee Robusta',
                'Pepper', 'Sugar', 'Wood', 'Steel', 'Construction materials',
                'Cement', 'Fertilizer', 'Coal', 'Petroleum', 'Manufacturing',
                'Fishery', 'Meat', 'Total tonnage']

    remove_routes_ids = [
        ('watern_149', 'watern_429'),
        ('watern_429', 'watern_520'),
        ('watern_700', 'watern_520'),
        ('watern_210', 'watern_700'),
        ('watern_209', 'watern_210'),
        ('watern_1057', 'watern_1050'),
        ('watern_1050', 'watern_1051'),
        ('watern_1051', 'watern_183'),
        ('watern_183', 'watern_354'),
        ('watern_176', 'watern_354'),
    ]

    for c in range(len(columns)):
        ax = get_axes()
        plot_basemap(ax, config['paths']['data'],highlight_region=[])
        scale_bar(ax, location=(0.8, 0.05))
        plot_basemap_labels(ax, config['paths']['data'])
        proj_lat_lon = ccrs.PlateCarree()

        column = columns[c]
        weights = [
                record['max_tons']
                for iter_, record in inland_edge_file.iterrows()
            ]
        max_weight = max(weights)
        width_by_range = generate_weight_bins(weights)

        geoms_by_range = {}
        for value_range in width_by_range:
            geoms_by_range[value_range] = []

        for iter_, record in inland_edge_file.iterrows():
            val = record[column]
            geom = record.geometry
            edge_id = (record['from_node'], record['to_node'])

            if val > 0 and (edge_id not in remove_routes_ids):  # only add edges that carry this commodity
                for nmin, nmax in geoms_by_range:
                    if nmin <= val and val < nmax:
                        geoms_by_range[(nmin, nmax)].append(geom)

        # plot
        for range_, width in width_by_range.items():
            ax.add_geometries(
                [geom.buffer(width) for geom in geoms_by_range[range_]],
                crs=proj_lat_lon,
                edgecolor='none',
                facecolor=color,
                zorder=2)

        x_l = 102.3
        x_r = x_l + 0.4
        base_y = 14
        y_step = 0.4
        y_text_nudge = 0.1
        x_text_nudge = 0.1

        ax.text(
            x_l,
            base_y + y_step - y_text_nudge,
            legend_label,
            horizontalalignment='left',
            transform=proj_lat_lon,
            size=10)

        divisor = column_label_divisors[column]
        for (i, ((nmin, nmax), width)) in enumerate(width_by_range.items()):
            y = base_y - (i*y_step)
            line = LineString([(x_l, y), (x_r, y)])
            ax.add_geometries(
                [line.buffer(width)],
                crs=proj_lat_lon,
                linewidth=0,
                edgecolor=color,
                facecolor=color,
                zorder=2)
            if nmin == max_weight:
                label = '>{:.2f}'.format(max_weight/divisor)
            else:
                label = '{:.2f}-{:.2f}'.format(nmin/divisor, nmax/divisor)
            ax.text(
                x_r + x_text_nudge,
                y - y_text_nudge,
                label,
                horizontalalignment='left',
                transform=proj_lat_lon,
                size=10)

        plt.title(title_cols[c], fontsize=14)
        output_file = os.path.join(config['paths']['figures'],
                                   'inland_flow-map-{}-max-scale.png'.format(column))
        save_fig(output_file)
        plt.close()


if __name__ == '__main__':
    main()
