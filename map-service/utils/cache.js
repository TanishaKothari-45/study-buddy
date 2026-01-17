import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CACHE_DIR = process.env.CACHE_DIR || path.join(__dirname, '../cache');

// Ensure cache directory exists
if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
}

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
    const pngPath = path.join(CACHE_DIR, `${hash}.png`);
    const metaPath = path.join(CACHE_DIR, `${hash}.meta.json`);

    if (fs.existsSync(svgPath)) {
        const svgContent = fs.readFileSync(svgPath, 'utf8');
        const base64 = Buffer.from(svgContent).toString('base64');
        const png_base64 = fs.existsSync(pngPath) ? fs.readFileSync(pngPath).toString('base64') : null;

        let meta = {};
        if (fs.existsSync(metaPath)) {
            meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
        }

        return { base64, png_base64, meta, svgContent };
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
    const pngPath = path.join(CACHE_DIR, `${hash}.png`);
    const metaPath = path.join(CACHE_DIR, `${hash}.meta.json`);

    fs.writeFileSync(svgPath, result.svgContent);
    if (result.pngBase64) {
        fs.writeFileSync(pngPath, Buffer.from(result.pngBase64, 'base64'));
    }
    fs.writeFileSync(metaPath, JSON.stringify(result.meta, null, 2));
}

export {
    getMapHash,
    getCached,
    saveCache
};
