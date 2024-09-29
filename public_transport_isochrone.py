import json
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Load the transport network data
with open('overpass_cache.json', 'r') as f:
    data = json.load(f)

# Create a graph for the transport network
G = nx.MultiDiGraph()


# Add nodes and edges to the graph
from tqdm import tqdm

for element in tqdm(data['elements'], desc="Processing public transport route"):
    if element['type'] == 'relation':
        for member in tqdm(element['members'], desc="Processing members", leave=False):
            local_node = []
            if member['type'] == 'node':
                node = member
                if node:
                    G.add_node(node['ref'], x=node['lon'], y=node['lat'], osmid=node['ref'], role="station")
                    local_node.append(node['ref'])
            elif member['type'] == 'way':
                way = member
                if way and 'geometry' in way:
                    for i in tqdm(range(len(way['geometry']) - 1), desc="Processing geometry", leave=False):
                        start_lat, start_lon = way['geometry'][i]['lat'], way['geometry'][i]['lon']
                        end_lat, end_lon = way['geometry'][i+1]['lat'], way['geometry'][i+1]['lon']
                        
                        # Check if nodes already exist, if not create new ones
                        start_node = next((node for node in local_node if G.nodes[node]['y'] == start_lat and G.nodes[node]['x'] == start_lon), None)
                        if start_node is None:
                            start_node = f"{start_lat},{start_lon}"
                            G.add_node(start_node, x=start_lon, y=start_lat, osmid=start_node)
                        
                        end_node = next((node for node in local_node if G.nodes[node]['y'] == end_lat and G.nodes[node]['x'] == end_lon), None)
                        if end_node is None:
                            end_node = f"{end_lat},{end_lon}"
                            G.add_node(end_node, x=end_lon, y=end_lat, osmid=end_node)
                        
                        if 'tags' in way and 'railway' in way['tags']:
                            G.add_edge(start_node, end_node, weight=1/60, length=1, highway='railway')  # Train speed: 60 km/h
                        else:
                            G.add_edge(start_node, end_node, weight=1/30, length=1, highway='bus')  # Bus speed: 30 km/h


# Add walking edges
# walking_speed = 3  # km/h
# for node, data in G.nodes(data=True):
#     if data.get('role') != "station":
#         continue
#     for neighbor in G.neighbors(node):
#         start = Point(G.nodes[node]['lon'], G.nodes[node]['lat'])
#         end = Point(G.nodes[neighbor]['lon'], G.nodes[neighbor]['lat'])
#         distance = start.distance(end) * 111  # Approximate conversion to km
#         walking_time = distance / walking_speed
#         G.add_edge(node, neighbor, weight=walking_time)

# Project the graph to UTM
G.graph['crs'] = 'EPSG:4326'
G = ox.project_graph(G)

print(f"Graph projected to CRS: {G.graph['crs']}")


class IsochroneRequest(BaseModel):
    lat: float
    lon: float
    time: int

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("public_transport_isochrone.html", {"request": request})

@app.post("/isochrone")
async def calculate_isochrone(request: IsochroneRequest):
    print(request)
    start_point = ox.nearest_nodes(G, request.lat, request.lon)
    
    # Calculate the isochrone
    subgraph = nx.ego_graph(G, start_point, radius=request.time, distance='weight')
    
    # Create a GeoDataFrame from the subgraph
    nodes = list(subgraph.nodes(data=True))
    gdf_nodes = gpd.GeoDataFrame(nodes, columns=['node', 'data'])
    gdf_nodes['geometry'] = gdf_nodes.apply(lambda row: Point(row['data']['lon'], row['data']['lat']), axis=1)
    gdf_nodes.set_geometry('geometry', inplace=True)
    
    # Create a convex hull to represent the isochrone
    isochrone = gdf_nodes.unary_union.convex_hull
    
    # Convert the isochrone to GeoJSON
    isochrone_geojson = gpd.GeoSeries([isochrone]).to_json()
    
    return {"isochrone": json.loads(isochrone_geojson)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
