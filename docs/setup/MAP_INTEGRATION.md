# Map Generation Integration - Quick Start

## ✅ What's Been Set Up

### 1. Node.js Microservice (`map-service/`)
- **Express server** on port 3001
- **D3 + TopoJSON** map generation
- **Hash-based caching** for performance
- **Multiple map types**: choropleth, markers, rivers, arrows, combined

### 2. Data Files (`map-service/data/`)
- ✅ `india_states_v1.topojson` - India state boundaries
- ✅ `world_countries_v1.topojson` - World country boundaries  
- ✅ `india_rivers_v1.geojson` - River networks

### 3. Prompt Engineering
- ✅ Added `MAP_GENERATION_RULES` to `shared_mains_prompts.py`
- ✅ Comprehensive examples for LLM guidance
- ✅ Use cases and coordinate references

## 🚀 Next Steps

### 1. Start the Map Service
```bash
cd map-service
npm start
```

Service will run on `http://localhost:3001`

### 2. Test the Service
```bash
curl -X POST http://localhost:3001/generate-map \
  -H "Content-Type: application/json" \
  -d '{
    "mapType": "markers",
    "topoKey": "india_states_v1",
    "region": "india",
    "title": "Test Map",
    "markers": [
      {"name": "Delhi", "coordinates": [77.2, 28.6], "type": "city", "label": "Delhi"}
    ]
  }'
```

### 3. Create Python Proxy (`backend/app/routes/map_proxy.py`)
This will:
- Parse `map-json` blocks from LLM output
- Call the Node microservice
- Return base64-embedded SVG images

### 4. Integrate into Answer Flow
- Update answer generation to parse map-json blocks
- Call map proxy to generate SVGs
- Embed in markdown output

## 📋 Pending Tasks

- [ ] Create Python proxy endpoint (`map_proxy.py`)
- [ ] Add map parsing to answer generation flow
- [ ] Configure map service URL in config
- [ ] Test with real LLM-generated maps
- [ ] Verify caching works correctly

## 🗺️ Map Types Supported

1. **Choropleth**: State/country-level data visualization
2. **Markers**: Point locations (cities, resources)
3. **Rivers**: River network overlays
4. **Arrows**: Directional flows (monsoons, trade routes)
5. **Combined**: Multiple layers together

## 📝 Example LLM Output

The LLM will now generate map-json blocks like:

```map-json
{
  "type": "map",
  "mapType": "choropleth",
  "region": "india",
  "title": "Rice Production by State",
  "choropleth": {
    "values": {"Punjab": 11.82, "West Bengal": 15.75},
    "unit": "million tonnes"
  },
  "legendTitle": "Rice Production",
  "style": {"colorScheme": "YlGn", "theme": "warm"}
}
```

This will be automatically converted to an SVG map and embedded in the answer.

## 🎯 Current Status

✅ **Setup Complete**: Microservice, data files, and prompts ready
⏳ **Next**: Python integration and testing
