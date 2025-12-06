import fs from 'fs';
import path from 'path';
import * as d3 from 'd3';
import { JSDOM } from 'jsdom';
import * as topojson from 'topojson-client';
import { fileURLToPath } from 'url';
import { getProjection } from './utils/projections.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Generate map SVG from configuration
 * @param {Object} config - Map configuration
 * @returns {Object} - {svgContent, meta, base64}
 */
async function generateMap(config) {
    console.log('🗺️ Map Service v1.3 - World Map Support');
    
    // Extract region first to determine default topoKey
    const regionValue = config.region || 'india';
    
    // Set topoKey based on region if not explicitly provided
    const defaultTopoKey = regionValue === 'world' ? 'world_countries_v1' : 'india_states_v1';
    
    const {
        mapType = 'combined',
        topoKey = defaultTopoKey,
        region = regionValue,
        width = region === 'world' ? 800 : 900,
        height = region === 'world' ? 450 : 1100,
        projection: projectionOverride = {},
        choropleth = null,
        markers = [],
        arrows = [],
        rivers = false,
        title = '',
        legendTitle = '',
        style = {},
        output = { format: 'svg' }
    } = config;
    
    console.log(`🌍 Region: ${region}, TopoKey: ${topoKey}`);

    // Load TopoJSON
    const topoPath = path.join(__dirname, 'data', `${topoKey}.topojson`);
    console.log(`📂 Loading TopoJSON from: ${topoPath}`);

    if (!fs.existsSync(topoPath)) {
        console.error(`❌ TopoJSON file not found: ${topoPath}`);
        throw new Error(`TopoJSON file not found: ${topoKey}`);
    }

    const topo = JSON.parse(fs.readFileSync(topoPath, 'utf8'));
    const objectKey = Object.keys(topo.objects)[0];
    console.log(`   TopoJSON loaded. Object key: ${objectKey}`);

    const geoData = topojson.feature(topo, topo.objects[objectKey]);
    console.log(`   Features extracted: ${geoData.features.length}`);

    // Load rivers if requested
    let riversData = null;
    if (rivers) {
        const riversPath = path.join(__dirname, 'data', `${region}_rivers_v1.geojson`);
        if (fs.existsSync(riversPath)) {
            riversData = JSON.parse(fs.readFileSync(riversPath, 'utf8'));
        }
    }

    // Create DOM
    const dom = new JSDOM('<!DOCTYPE html><body></body>');
    const body = d3.select(dom.window.document.querySelector('body'));

    // Create SVG with viewBox for responsive sizing
    const svg = body.append('svg')
        .attr('xmlns', 'http://www.w3.org/2000/svg')
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('width', '100%')
        .attr('height', '100%')
        .attr('preserveAspectRatio', 'xMidYMid meet');

    // === DEBUG: Log geoData before projection ===
    console.log('--- DEBUG: geoData type and feature count ---');
    if (geoData) {
        console.log('  geoData.features?.length =', geoData.features?.length);
        console.log('  geoData sample feature type =', geoData.features?.[0]?.geometry?.type);
        console.log('  geoData sample feature name =', geoData.features?.[0]?.properties?.name || geoData.features?.[0]?.properties?.NAME);
        console.log('  geoData bbox =', JSON.stringify(d3.geoBounds(geoData)));
    } else {
        console.log('  geoData is null/undefined');
    }
    console.log('--- END DEBUG ---');

    // Set up projection - pass geoData for automatic fitSize calculation
    const projection = getProjection(region, width, height, projectionOverride, geoData);
    const pathGenerator = d3.geoPath().projection(projection);

    // Styling
    const colorScheme = style.colorScheme || 'YlGn';
    const riverColor = style.riverColor || '#1f78b4';
    const theme = style.theme || 'warm';

    const bgColor = theme === 'warm' ? '#faf8f5' : '#ffffff';
    const landColor = theme === 'warm' ? '#e6e0d4' : '#f0f0f0'; // Darker warm beige
    const borderColor = theme === 'warm' ? '#9c9891' : '#a0a0a0'; // Darker border
    // Darker border

    // Background
    svg.append('rect')
        .attr('width', width)
        .attr('height', height)
        .attr('fill', bgColor);

    // Draw base map
    console.log('🗺️ Drawing base map...');
    console.log('   Feature count:', geoData.features.length);

    if (geoData.features.length > 0) {
        const firstPath = pathGenerator(geoData.features[0]);
        console.log('   First feature path length:', firstPath ? firstPath.length : 0);
        console.log('   First feature path start:', firstPath ? firstPath.substring(0, 50) : 'null');
    }

    svg.append('g')
        .attr('id', 'base-map')
        .selectAll('path')
        .data(geoData.features)
        .enter()
        .append('path')
        .attr('d', pathGenerator)
        .attr('fill', landColor)
        .attr('stroke', borderColor)
        .attr('stroke-width', 0.5);

    // Choropleth layer
    if (choropleth && (mapType === 'choropleth' || mapType === 'combined')) {
        const values = choropleth.values || {};
        const valueArray = Object.values(values).filter(v => !isNaN(v));

        if (valueArray.length > 0) {
            const vmin = d3.min(valueArray);
            const vmax = d3.max(valueArray);

            // Get color interpolator
            let colorInterpolator;
            switch (colorScheme) {
                case 'YlGn': colorInterpolator = d3.interpolateYlGn; break;
                case 'YlOrRd': colorInterpolator = d3.interpolateYlOrRd; break;
                case 'Blues': colorInterpolator = d3.interpolateBlues; break;
                case 'Greens': colorInterpolator = d3.interpolateGreens; break;
                default: colorInterpolator = d3.interpolateYlGn;
            }

            const colorScale = d3.scaleSequential(colorInterpolator).domain([vmin, vmax]);

            svg.append('g')
                .attr('id', 'choropleth')
                .selectAll('path')
                .data(geoData.features)
                .enter()
                .append('path')
                .attr('d', pathGenerator)
                .attr('fill', d => {
                    const name = (d.properties.NAME_1 || d.properties.name || d.properties.NAME || '').toString().trim();
                    const value = values[name];
                    return (value != null && !isNaN(value)) ? colorScale(value) : 'none';
                })
                .attr('stroke', borderColor)
                .attr('stroke-width', 0.5)
                .attr('opacity', 0.85);

            // Add legend
            addLegend(svg, width, height, vmin, vmax, colorScale, legendTitle, choropleth.unit);
        }
    }

    // Rivers layer
    if (riversData && (mapType === 'rivers' || mapType === 'combined')) {
        svg.append('g')
            .attr('id', 'rivers')
            .selectAll('path')
            .data(riversData.features)
            .enter()
            .append('path')
            .attr('d', pathGenerator)
            .attr('fill', 'none')
            .attr('stroke', riverColor)
            .attr('stroke-width', d => (d.properties && d.properties.major ? 1.8 : 1.0))
            .attr('opacity', 0.7);
    }

    // Markers layer
    if (markers && markers.length > 0 && (mapType === 'markers' || mapType === 'combined')) {
        const markerGroup = svg.append('g').attr('id', 'markers');

        markers.forEach(marker => {
            const coords = projection(marker.coordinates);
            if (coords) {
                const [x, y] = coords;

                // Marker circle
                const markerColor = getMarkerColor(marker.type);
                markerGroup.append('circle')
                    .attr('cx', x)
                    .attr('cy', y)
                    .attr('r', 8) // Increased radius
                    .attr('fill', markerColor)
                    .attr('stroke', '#333')
                    .attr('stroke-width', 1.5);

                // Label
                if (marker.label) {
                    markerGroup.append('text')
                        .attr('x', x)
                        .attr('y', y - 12)
                        .attr('text-anchor', 'middle')
                        .attr('font-size', 14) // Increased font size
                        .attr('font-weight', '600')
                        .attr('fill', '#222')
                        .text(marker.label);
                }
            }
        });
    }

    // Arrows layer
    if (arrows && arrows.length > 0 && (mapType === 'arrows' || mapType === 'combined')) {
        // Define arrowhead marker
        const defs = svg.append('defs');
        defs.append('marker')
            .attr('id', 'arrowhead')
            .attr('markerWidth', 10)
            .attr('markerHeight', 10)
            .attr('refX', 8)
            .attr('refY', 3)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,0 L0,6 L9,3 z')
            .attr('fill', '#d73027');

        const arrowGroup = svg.append('g').attr('id', 'arrows');

        arrows.forEach(arrow => {
            const p1 = projection(arrow.from);
            const p2 = projection(arrow.to);

            if (p1 && p2) {
                const dx = p2[0] - p1[0];
                const dy = p2[1] - p1[1];
                const cx = p1[0] + dx * 0.4 - dy * 0.2;
                const cy = p1[1] + dy * 0.4 + dx * 0.2;

                arrowGroup.append('path')
                    .attr('d', `M${p1[0]},${p1[1]} Q${cx},${cy} ${p2[0]},${p2[1]}`)
                    .attr('fill', 'none')
                    .attr('stroke', '#d73027')
                    .attr('stroke-width', 2)
                    .attr('marker-end', 'url(#arrowhead)')
                    .attr('opacity', 0.8);

                // Arrow label
                if (arrow.label) {
                    arrowGroup.append('text')
                        .attr('x', cx)
                        .attr('y', cy - 5)
                        .attr('text-anchor', 'middle')
                        .attr('font-size', 10)
                        .attr('fill', '#d73027')
                        .text(arrow.label);
                }
            }
        });
    }

    // Title
    if (title) {
        svg.append('text')
            .attr('x', 20)
            .attr('y', 30)
            .attr('font-size', 18)
            .attr('font-weight', '600')
            .attr('fill', '#333')
            .text(title);
    }

    // Source attribution
    svg.append('text')
        .attr('x', 20)
        .attr('y', height - 10)
        .attr('font-size', 10)
        .attr('fill', '#666')
        .text('Source: Natural Earth / Study Buddy');

    // Extract SVG
    const svgContent = body.html();
    const base64 = Buffer.from(svgContent).toString('base64');

    // Metadata
    const meta = {
        width,
        height,
        region,
        mapType,
        markerCount: markers.length,
        arrowCount: arrows.length,
        hasRivers: !!riversData,
        hasChoropleth: !!choropleth
    };

    console.log('✅ Map generation completed successfully');
    return { svgContent, base64, meta };
}

/**
 * Add legend to SVG
 */
function addLegend(svg, width, height, vmin, vmax, colorScale, title, unit) {
    const legendW = 180;
    const legendH = 12;
    const legendX = width - legendW - 30;
    const legendY = height - 90;

    // Gradient
    const gradId = 'legendGrad';
    const defs = svg.select('defs').empty() ? svg.append('defs') : svg.select('defs');
    const gradient = defs.append('linearGradient')
        .attr('id', gradId)
        .attr('x1', '0%')
        .attr('x2', '100%');

    for (let i = 0; i <= 5; i++) {
        gradient.append('stop')
            .attr('offset', `${(i / 5) * 100}%`)
            .attr('stop-color', colorScale(vmin + (vmax - vmin) * (i / 5)));
    }

    // Legend rect
    svg.append('rect')
        .attr('x', legendX)
        .attr('y', legendY)
        .attr('width', legendW)
        .attr('height', legendH)
        .attr('fill', `url(#${gradId})`)
        .attr('stroke', '#999')
        .attr('stroke-width', 0.5);

    // Title
    svg.append('text')
        .attr('x', legendX)
        .attr('y', legendY - 8)
        .attr('font-size', 11)
        .attr('font-weight', '500')
        .text(title);

    // Min/Max labels
    const unitStr = unit ? ` ${unit}` : '';
    svg.append('text')
        .attr('x', legendX)
        .attr('y', legendY + legendH + 14)
        .attr('font-size', 10)
        .text(`${vmin.toFixed(1)}${unitStr}`);

    svg.append('text')
        .attr('x', legendX + legendW)
        .attr('y', legendY + legendH + 14)
        .attr('text-anchor', 'end')
        .attr('font-size', 10)
        .text(`${vmax.toFixed(1)}${unitStr}`);
}

/**
 * Get marker color based on type
 */
function getMarkerColor(type) {
    const colors = {
        coal: '#2c2c2c',
        iron: '#8b4513',
        gold: '#ffd700',
        copper: '#b87333',
        city: '#4a90e2',
        port: '#1e88e5',
        default: '#ff6600'
    };
    return colors[type] || colors.default;
}

export {
    generateMap
};
