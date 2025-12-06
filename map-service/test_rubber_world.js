import { generateMap } from './generate_map.js';
import fs from 'fs';

const config = {
    "type": "map",
    "mapType": "markers",
    "region": "world",
    "title": "Major Rubber Producing Countries",
    "markers": [
        {
            "name": "Thailand",
            "coordinates": [100.5, 13.7],
            "type": "crop",
            "label": "Thailand"
        },
        {
            "name": "Indonesia",
            "coordinates": [106.8, -6.2],
            "type": "crop",
            "label": "Indonesia"
        },
        {
            "name": "Vietnam",
            "coordinates": [105.8, 21],
            "type": "crop",
            "label": "Vietnam"
        },
        {
            "name": "Malaysia",
            "coordinates": [101.9, 4.2],
            "type": "crop",
            "label": "Malaysia"
        },
        {
            "name": "India",
            "coordinates": [76.2, 9.9],
            "type": "crop",
            "label": "India (Kerala)"
        },
        {
            "name": "China",
            "coordinates": [102.7, 25],
            "type": "crop",
            "label": "China (Yunnan)"
        }
    ],
    "style": {
        "theme": "warm"
    }
};

console.log('🧪 Testing World Map Generation');
console.log('Config:', JSON.stringify(config, null, 2));
console.log('');

try {
    const result = await generateMap(config);
    console.log('\n✅ Map generated successfully');
    console.log('SVG length:', result.svgContent.length);
    
    // Save to file for inspection
    fs.writeFileSync('./test_rubber_world_output.svg', result.svgContent);
    console.log('📁 Saved to: test_rubber_world_output.svg');
    
} catch (error) {
    console.error('❌ Error:', error.message);
    console.error(error.stack);
}
