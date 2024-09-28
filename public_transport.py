import json
import folium
from collections import defaultdict
from haversine import haversine

# Load data from overpass_cache.json
with open('overpass_cache.json', 'r') as f:
    data = json.load(f)

# Create a map centered on Jakarta
jakarta_coords = (-6.2088, 106.8456)  # Latitude and longitude for Jakarta
m = folium.Map(location=jakarta_coords, zoom_start=11, tiles='CartoDB positron')

# Create a FeatureGroup for each relation
feature_groups = defaultdict(folium.FeatureGroup)

# Iterate through the relations (routes) in the data
for element in data['elements']:
    if element['type'] == 'relation':
        relation_id = element['id']
        route_name = element.get('tags', {}).get('name', f'Unnamed route {relation_id}')
        # Generate a unique color for this relation
        color = f'#{abs(hash(route_name)) % 0xFFFFFF:06x}'
        
        # Create a new FeatureGroup for this relation if it doesn't exist
        if relation_id not in feature_groups:
            feature_groups[relation_id] = folium.FeatureGroup(name=route_name, show=True)
        
        # Collect all coordinates for this route
        coordinates = []
        for member in element['members']:
            if member['type'] == 'way' and 'geometry' in member:
                for point in member['geometry']:
                    if not coordinates or haversine(coordinates[-1], (point['lat'], point['lon'])) < 2:
                        coordinates.append((point['lat'], point['lon']))
        
        # Apply a small offset to the coordinates
        offset = 0.00001 * (relation_id % 10 - 5)  # This creates a range of offsets from -0.0005 to 0.0005
        offset_coordinates = [(lat + offset, lon + offset) for lat, lon in coordinates]
        
        # Draw the route on the map
        folium.PolyLine(
            locations=offset_coordinates,
            color=color,
            weight=2,
            opacity=0.8,
            tooltip=route_name
        ).add_to(feature_groups[relation_id])

# Add all feature groups to the map in alphabetical order
for fg in sorted(feature_groups.values(), key=lambda x: x.layer_name):
    fg.add_to(m)

# Add layer control to toggle routes on/off
folium.LayerControl().add_to(m)

# Save the map as an HTML file
m.save("public_transport.html")

print("Map has been saved as public_transport.html")