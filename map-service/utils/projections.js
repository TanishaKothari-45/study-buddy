import * as d3 from 'd3';

/**
 * Get projection configuration for different regions
 * @param {string} region - 'india' or 'world'
 * @param {number} width - Map width
 * @param {number} height - Map height
 * @param {Object} override - Optional projection override
 * @param {Object} geoData - Optional GeoJSON data for fitSize calculation
 * @returns {Object} - D3 projection
 */
function getProjection(region, width, height, override = {}, geoData = null) {
    // Define region-specific configurations
    const configs = {
        india: {
            type: 'geoMercator',
            // India bounds: roughly 68-97°E, 8-35°N
            // Using fitExtent with padding for better display
            padding: 40
        },
        world: {
            type: 'geoNaturalEarth1',
            center: [0, 0],
            scale: 180,
            translate: [width / 2, height / 2]
        }
    };

    const config = configs[region] || configs.world;

    // Apply overrides
    const finalConfig = { ...config, ...override };

    // Create projection
    let projection;
    switch (finalConfig.type) {
        case 'geoMercator':
            projection = d3.geoMercator();
            break;
        case 'geoNaturalEarth1':
            projection = d3.geoNaturalEarth1();
            break;
        case 'geoAlbers':
            projection = d3.geoAlbers();
            break;
        default:
            projection = d3.geoMercator();
    }

    // If geoData is provided, use fitExtent to auto-calculate scale and translate
    if (geoData && region === 'india') {
        const padding = finalConfig.padding || 40;
        projection.fitExtent(
            [[padding, padding], [width - padding, height - padding]],
            geoData
        );
        console.log('   Projection fitted to geoData bounds');
    } else if (finalConfig.center && finalConfig.scale) {
        // Fall back to manual configuration
        projection
            .center(finalConfig.center)
            .scale(finalConfig.scale)
            .translate(finalConfig.translate || [width / 2, height / 2]);
    }

    return projection;
}

export {
    getProjection
};
