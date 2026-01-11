# Map Generation Microservice

Server-side SVG map generation using D3 + TopoJSON for UPSC study materials.

## Features

- **Multiple map types**: Choropleth, markers, rivers, arrows, and combined
- **Regions**: India and World maps
- **Caching**: Hash-based caching for performance
- **Flexible styling**: Customizable colors, themes, and projections
- **Base64 output**: Easy embedding in markdown/HTML

## Setup

```bash
cd map-service
npm install
npm start
```

Service runs on `http://localhost:3001`

## API Endpoints

### POST /generate-map

Generate a map from JSON configuration.

**Request body:**
```json
{
  "mapType": "combined",
  "topoKey": "india_states_v1",
  "region": "india",
  "width": 900,
  "height": 1100,
  "choropleth": {
    "values": { "Punjab": 12, "Haryana": 8 },
    "unit": "million tonnes"
  },
  "markers": [
    { "name": "Delhi", "coordinates": [77.2, 28.6], "type": "city", "label": "Delhi" }
  ],
  "arrows": [
    { "from": [72, 5], "to": [80, 22], "label": "SW Monsoon" }
  ],
  "rivers": true,
  "title": "Wheat Production in India",
  "legendTitle": "Production",
  "style": { "colorScheme": "YlGn", "theme": "warm" }
}
```

**Response:**
```json
{
  "svg_url": "/maps/abc123.svg",
  "svg_base64": "PHN2Zy4uLg==",
  "meta": { "width": 900, "height": 1100 },
  "cached": false,
  "hash": "abc123"
}
```

### GET /health

Health check endpoint.

### GET /available-maps

List available TopoJSON/GeoJSON files.

## Data Files

Place TopoJSON and GeoJSON files in `map-service/data/`:

- `india_states_v1.topojson` - India state boundaries
- `india_rivers_v1.geojson` - India river network
- `world_countries_v1.topojson` - World country boundaries

## Map Types

- **choropleth**: Color-coded regions based on data values
- **markers**: Point locations (cities, resources)
- **rivers**: River networks
- **arrows**: Directional flows (monsoons, trade routes)
- **combined**: Multiple layers together

## Color Schemes

- `YlGn` - Yellow to Green (crops, vegetation)
- `YlOrRd` - Yellow to Orange to Red (temperature, intensity)
- `Blues` - Blue scale (water, rainfall)
- `Greens` - Green scale (forest cover)

## Caching

Maps are cached based on request hash. Cached files stored in `../backend/map_storage/`.
