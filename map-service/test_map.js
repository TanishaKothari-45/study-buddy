import { generateMap } from './generate_map.js';

const config = {
    region: 'india',
    width: 800,
    height: 600
};

try {
    console.log("Starting map generation...");
    await generateMap(config);
    console.log("Map generation finished.");
} catch (error) {
    console.error("Error running generateMap:", error);
}
