"""Pre-process CVTS traces

Purpose
-------
Process CVTS (Commercial Vehicle Tracking System) GPS traces. The script first reduces
the number of Cvts points by removing standstill and minimal movement from the dataset.
Each GPS trace is then mapped on the road network and  processed into a route (a list
of road edge id's). The sum of vehicles passing a each edge is added it the road
network shapefile.

Input data requirements
-----------------------
Correct paths to all files and correct input parameter

1) All Cvts data files must be defined as csv-files with column positions holding the following data:
- Position 3: Lattitude
- Position 4: Longitude
- Position 9: Timestamp

2) Road edge shapefile must contain valid LineString geometries with the following attributes
- G_ID: A unique ID that identifies the road edge

Results
-------
1) Each Cvts trace is processed into a route
- A list of road edge id's

2) The road edge shapefile is appended with the following properties:
- vehicle_count: The total number of vehicles that passed this edge

References
----------
1. Pant, R., Koks, E.E., Russell, T., Schoenmakers, R. & Hall, J.W. (2018).
   Analysis and development of model for addressing climate change/disaster risks in multi-modal transport networks in Vietnam.
   Final Report, Oxford Infrastructure Analytics Ltd., Oxford, UK.
2. All input data folders and files referred to in the code below.

"""
import csv
import os
import sys
import time
from collections import OrderedDict, defaultdict
from pathlib import Path
import zipfile

import fiona
from rtree import index
from shapely.geometry import LineString, MultiLineString, Point, mapping, shape
from vtra.utils import load_config


def main():
    """Pre-process CVTS
    """
    incoming_root = load_config()['paths']['incoming_data']
    data_root = load_config()['paths']['data']
    output_root = load_config()['paths']['output']

    dir_raw_roads = os.path.join(data_root, 'post_processed_networks')
    dir_raw_cvts = os.path.join(incoming_root,'20170801')
    

    dir_inter_reduse = os.path.join(output_root, 'transport cvts analysis', 'intermediate', 'reduse')
    dir_results_routes = os.path.join(output_root, 'transport cvts analysis', 'results', 'routes')
    
    dir_results_routes_collected = os.path.join(
        output_root, 'transport cvts analysis', 'results', 'routes_collected')
    dir_results_traffic_count = os.path.join(output_root, 'transport cvts analysis', 'results', 'traffic_count')

    Reduse dataset with 70 percent (processing 4s/100mb)
    print('Reduce dataset size')
    reduse_dataset(dir_raw_cvts, dir_inter_reduse)

    # Read road network in memory
    print('Read road network')
    geojson_road_network = read_shapefile(dir_raw_roads, 'road_edges.shp')

    # Generate routes by mapping gps points on the road network
    print('Generate routes')
    find_routes(geojson_road_network, dir_inter_reduse, dir_results_routes)

    # add traffic attribute to route network (count id's in routes)
    print('Add traffic count attribute to road network')
    geojson_road_network = add_traffic_count_to_road_network(
        geojson_road_network, dir_results_routes, dir_results_traffic_count)

    write_shapefile(geojson_road_network, dir_results_traffic_count, 'road_network.shp')

    # add routes to single file
    create_single_route_file(dir_results_routes, dir_results_routes_collected)


def reduse_dataset(source_dir, dest_dir):
    # Reduce the size of the dataset to speed up further processing
    # and output this in an intermediate mirror dataset
    #
    # MIN_MOV:
    #   0.001: is a good setting to remove all standstill (
    #        69.276 items (13.5GB) -> 69.261 items (8.4GB))

    MIN_LAT_MOV = 0.001
    MIN_LON_MOV = 0.001

    # MIN_SAMPLE:
    #   0.01: is a good setting for national road analysis
    #         reduces dataset to 69, 261 items, totalling 246.2 MB
    MIN_LAT_SAMPLE = 0.01
    MIN_LON_SAMPLE = 0.01

    # Mirror the data that is used in the intermediate folder
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".csv"):
                rel_path = os.path.relpath(root, source_dir)

                with open(os.path.join(root, file), 'rt') as source:
                    target = os.path.join(dest_dir, rel_path)
                    Path(os.path.join(dest_dir, rel_path)).mkdir(parents=True, exist_ok=True)

                    with open(os.path.join(target, file), 'wt') as sink:
                        reader = csv.reader(source)

                        # Remove rows that are not used
                        # This leaves it with, Lattitude, Longitude, Time
                        data = [[row[2], row[3], row[8]] for row in reader]

                        # Remove rows that show minimal and maximal movement
                        # Minimal movements (vehicle standing still) can be removed
                        # because they don't provide useful information
                        data_moving = []
                        for previous, current in zip(data[1:-1], data[2:]):
                            lat_mov = abs(float(previous[0]) - float(current[0]))
                            lon_mov = abs(float(previous[1]) - float(current[1]))
                            if lat_mov >= MIN_LAT_MOV or lon_mov >= MIN_LON_MOV:

                                # Always add the first coordinate
                                if len(data_moving) == 0:
                                    data_moving.append(current)
                                # Only sample if interval is large enough
                                else:
                                    sample_lat_mov = abs(
                                        float(data_moving[-1][0]) - float(current[0]))
                                    sample_lon_mov = abs(
                                        float(data_moving[-1][1]) - float(current[1]))

                                    if sample_lat_mov >= MIN_LAT_SAMPLE or sample_lon_mov >= MIN_LON_SAMPLE:
                                        data_moving.append(current)

                        # Write clean dataset to file
                        wr = csv.writer(sink, delimiter=',')
                        [wr.writerow(row) for row in data_moving]


def process_gps_trace_into_points(source_dir):
    # Generate geojson format dictionaries from a gps point folder

    geojson = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".csv"):
                with open(os.path.join(root, file), 'rt') as source:
                    reader = csv.reader(source)

                    try:
                        next(reader)

                        for row in reader:
                            geojson.append({
                                'type': "Feature",
                                'geometry': {
                                    "type": "Point",
                                    "coordinates": [float(row[0]), float(row[1])]
                                },
                                'properties': {
                                    "id": file,
                                    "time": row[2]
                                }
                            })
                    except:
                        print('File ' + root + file + ' was not processed because of an issue')
    return geojson


def clip_gps_points(road_network, source_dir, dest_dir):

    # Build a polygon (convex hull) that represents data in the road network
    road_network_area = MultiLineString([shape(road['geometry'])
                                         for road in road_network]).convex_hull

    # Filter gps points that are not in this area
    # Mirror the data that is used in the source folder
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".csv"):
                rel_path = os.path.relpath(root, source_dir)

                with open(os.path.join(root, file), 'rt') as source:
                    target = os.path.join(dest_dir, rel_path)
                    Path(os.path.join(dest_dir, rel_path)).mkdir(parents=True, exist_ok=True)

                    with open(os.path.join(target, file), 'wt') as sink:
                        reader = csv.reader(source, quoting=csv.QUOTE_NONNUMERIC)

                        # Remove rows that are not covered by the road network
                        data = [row for row in reader if Point(
                            row[0], row[1]).within(road_network_area)]

                        # Write clean dataset to file
                        wr = csv.writer(sink, delimiter=',')
                        [wr.writerow(row) for row in data]


def find_routes(road_network, gps_points_folder, routes_folder):
    # Process gps points by comparing the route network agains the route
    # trace with a buffer around it
    # BUFFER_SIZE:
    #   0.00015: Good number for local analysis
    #   0.002:   Good number for national analysis
    BUFFER_SIZE = 0.002

    # NUM_RETURN_JOURNEY
    # Defines how many other edges must have been passed before
    # a previous driven edge it counted again (as a return journey)
    NUM_RETURN_JOURNEY = 5

    # Process road network into spatial index
    rtree = index.Index()
    road_network_lut = {}
    for road in road_network:
        rtree.insert(int(road['properties']['g_id']), shape(
            road['geometry']).bounds, obj=shape(road['geometry']))
        road_network_lut[int(road['properties']['g_id'])] = shape(road['geometry'])

    # Process gps points per file
    for root, dirs, files in os.walk(gps_points_folder):
        for file in files:
            if file.endswith(".csv"):
                rel_path = os.path.relpath(root, gps_points_folder)
                with open(os.path.join(root, file), 'rt') as source:
                    target = os.path.join(routes_folder, rel_path)
                    Path(os.path.join(routes_folder, rel_path)).mkdir(
                        parents=True, exist_ok=True)

                    with open(os.path.join(target, file), 'wt') as sink:
                        reader = csv.reader(source, quoting=csv.QUOTE_NONNUMERIC)

                        try:
                            data = [row for row in reader]

                            # Build the route
                            geom = LineString([Point(row[0], row[1]) for row in data])
                            timestamps = [row[2] for row in data]

                            route = []
                            for previous, current, timestamp in zip(list(geom.coords), list(geom.coords)[1:], timestamps):

                                route_segment = LineString([previous, current])
                                route_segment_buf = route_segment.buffer(BUFFER_SIZE)

                                for edge_id in list(rtree.intersection(route_segment_buf.bounds)):

                                    add_route_id = False

                                    # Keep long edges if its intersection is at least 90% of the line segment within buffer
                                    if road_network_lut[edge_id].intersection(route_segment_buf).length > route_segment.length * 0.8:
                                        add_route_id = True

                                    # Keep short edges if
                                    elif road_network_lut[edge_id].length < route_segment.length \
                                            and road_network_lut[edge_id].intersection(route_segment_buf).length > road_network_lut[edge_id].length * 0.7:
                                        add_route_id = True

                                    # Only add route id, if it doesnt exist in last x route points
                                    if add_route_id:
                                        if edge_id not in [row[0] for row in route[-NUM_RETURN_JOURNEY:]]:
                                            route.append([edge_id, timestamp])

                            # Write clean dataset to file
                            wr = csv.writer(sink, delimiter=',')
                            [wr.writerow(row) for row in route]
                        except:
                            print('Unable to find route for ' + file)


def add_traffic_count_to_road_network(road_network, routes_folder, results_folder):

    # Process road network into lookup friendly dictionary
    road_network_lut = {}
    for road in road_network:
        road_network_lut[int(road['properties']['g_id'])] = road
        road_network_lut[int(road['properties']['g_id'])]['properties']['vehicle_co'] = 0

    # Add vehicle count attribute to road network
    for root, dirs, files in os.walk(routes_folder):
        for file in files:
            if file.endswith(".csv"):
                rel_path = os.path.relpath(root, routes_folder)
                with open(os.path.join(root, file), 'rt') as source:
                    reader = csv.reader(source, quoting=csv.QUOTE_NONNUMERIC)

                    for route_edge in reader:
                        road_network_lut[int(route_edge[0])
                                         ]['properties']['vehicle_co'] += 1

    return [road[1] for road in road_network_lut.items()]


def create_single_route_file(routes_folder, routes_collected_folder):
    # The routes folder shows results in the same folder structure as the
    # raw data. This function collects all the routes and uses this to build
    # a single csv file.
    routes_collected = []
    for root, dirs, files in os.walk(routes_folder):
        for file in files:
            if file.endswith(".csv"):
                rel_path = os.path.relpath(root, routes_folder)
                with open(os.path.join(root, file), 'rt') as source:

                    reader = csv.reader(source, quoting=csv.QUOTE_NONNUMERIC)

                    data = [row for row in reader]

                    routes_collected.append({
                        'vehicle_id': file.replace('.csv', ''),
                        'edge_path': [int(elem[0]) for elem in data],
                        'time_stamp': [int(elem[1]) for elem in data]
                    })

    Path(routes_collected_folder).mkdir(parents=True, exist_ok=True)
    with open(os.path.join(routes_collected_folder, 'routes.csv'), 'wt') as sink:

        fieldnames = ['vehicle_id', 'edge_path', 'time_stamp']
        writer = csv.DictWriter(sink, fieldnames=fieldnames)

        writer.writeheader()
        [writer.writerow(route) for route in routes_collected]


def read_shapefile(path, file):
    with fiona.open(os.path.join(path, file), 'r') as source:
        return [entry for entry in source]


def write_shapefile(data, folder, filename):

    # Translate props to Fiona sink schema
    prop_schema = []
    for name, value in data[0]['properties'].items():
        fiona_prop_type = next((fiona_type for fiona_type, python_type in fiona.FIELD_TYPES_MAP.items(
        ) if python_type == type(value)), None)
        prop_schema.append((name, fiona_prop_type))

    new_prop_schema = []
    for prop in prop_schema:
        print(prop[1])
        if prop[1] == None:
            new_prop_schema.append((prop[0], 'str'))
        else:
            new_prop_schema.append(prop)

    sink_driver = 'ESRI Shapefile'
    sink_crs = {'init': 'epsg:4326'}
    sink_schema = {
        'geometry': data[0]['geometry']['type'],
        'properties': OrderedDict(new_prop_schema)
    }

    # Create path
    directory = os.path.join(folder)
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Write all elements to output file
    with fiona.open(os.path.join(directory, filename), 'w', driver=sink_driver, crs=sink_crs, schema=sink_schema) as sink:
        [sink.write(feature) for feature in data]


if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print('Script completed in: ' + str(round((end - start), 2)) + ' seconds.')
