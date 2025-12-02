import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CACHE_DIR = path.join(__dirname, '../../backend/map_storage');

/**
 * Generate a hash for the map request payload
 * @param {Object} payload - Map generation request
 * @returns {string} - 16-character hash
 */
function getMapHash(payload) {
    // Normalize the payload by sorting keys
    const normalized = JSON.stringify(payload, Object.keys(payload).sort());
    return crypto.createHash('sha256').update(normalized).digest('hex').substring(0, 16);
}

/**
 * Check if a cached map exists
 * @param {string} hash - Map hash
 * @returns {Object|null} - Cached data or null
 */
function getCached(hash) {
    const svgPath = path.join(CACHE_DIR, `${hash}.svg`);
    const metaPath = path.join(CACHE_DIR, `${hash}.meta.json`);

    if (fs.existsSync(svgPath)) {
        const svgContent = fs.readFileSync(svgPath, 'utf8');
        const base64 = Buffer.from(svgContent).toString('base64');

        let meta = {};
        if (fs.existsSync(metaPath)) {
            meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
        }

        return { base64, meta, svgContent };
    }

    return null;
}

/**
 * Save generated map to cache
 * @param {string} hash - Map hash
 * @param {Object} result - Generation result {svgContent, meta}
 */
function saveCache(hash, result) {
    const svgPath = path.join(CACHE_DIR, `${hash}.svg`);
    const metaPath = path.join(CACHE_DIR, `${hash}.meta.json`);

    fs.writeFileSync(svgPath, result.svgContent);
    fs.writeFileSync(metaPath, JSON.stringify(result.meta, null, 2));
}

export {
    getMapHash,
    getCached,
    saveCache
};
