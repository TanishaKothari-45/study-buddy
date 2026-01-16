import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { generateMap } from './generate_map.js';
import { getMapHash, getCached, saveCache } from './utils/cache.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Serve static maps
app.use('/maps', express.static(path.join(__dirname, '../backend/map_storage')));

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'ok', service: 'map-generation' });
});

// Main map generation endpoint
app.post('/generate-map', async (req, res) => {
    try {
        console.log('📍 Map generation request received');
        console.log('Config:', JSON.stringify(req.body, null, 2));

        // Generate hash for caching
        const hash = getMapHash(req.body);
        console.log(`🔑 Hash: ${hash}`);

        // Check cache
        const cached = getCached(hash);
        if (cached) {
            console.log('✅ Cache hit!');
            return res.json({
                svg_url: `/maps/${hash}.svg`,
                svg_base64: cached.base64,
                png_base64: cached.png_base64 || null,
                meta: cached.meta,
                cached: true,
                hash
            });
        }

        console.log('🔨 Generating new map...');

        // Generate map
        const startTime = Date.now();
        const result = await generateMap(req.body);
        const generationTime = Date.now() - startTime;

        console.log(`✅ Map generated in ${generationTime}ms`);

        // Save to cache
        saveCache(hash, result);

        console.log('📤 Sending successful response');
        res.json({
            svg_url: `/maps/${hash}.svg`,
            svg_base64: result.base64,
            png_base64: result.pngBase64 || null,
            meta: {
                ...result.meta,
                generationTime
            },
            cached: false,
            hash
        });

    } catch (error) {
        console.error('❌ Error generating map:', error);
        res.status(500).json({
            error: 'Failed to generate map',
            details: error.message,
            stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
        });
    }
});

// List available TopoJSON files
app.get('/available-maps', async (req, res) => {
    const fs = (await import('fs')).default;
    const dataDir = path.join(__dirname, 'data');

    try {
        const files = fs.readdirSync(dataDir)
            .filter(f => f.endsWith('.topojson') || f.endsWith('.geojson'))
            .map(f => ({
                name: f,
                type: f.endsWith('.topojson') ? 'topojson' : 'geojson',
                key: f.replace(/\.(topojson|geojson)$/, '')
            }));

        res.json({ files });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Start server
app.listen(PORT, () => {
    console.log(`🗺️  Map Generation Service running on port ${PORT}`);
    console.log(`📊 Health check: http://localhost:${PORT}/health`);
    console.log(`🎨 Generate map: POST http://localhost:${PORT}/generate-map`);
});
