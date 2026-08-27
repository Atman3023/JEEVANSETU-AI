/**
 * JeevanSetu AI - Centralized API Service
 * 
 * All backend communication goes through this module.
 * Handles errors, timeouts, and offline detection.
 */

class JeevanSetuAPI {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.timeout = 10000; // 10 seconds
    }

    /**
     * Internal fetch wrapper with timeout and error handling.
     */
    async _fetch(url, options = {}) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await fetch(this.baseUrl + url, {
                ...options,
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers,
                },
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                const errBody = await response.json().catch(() => ({}));
                const error = new Error(errBody.detail || `Server error (${response.status})`);
                error.status = response.status;
                throw error;
            }

            return await response.json();
        } catch (err) {
            clearTimeout(timeoutId);
            if (err.name === 'AbortError') {
                throw new Error('Request timed out. Please check your connection.');
            }
            if (!navigator.onLine) {
                throw new Error('You are offline. Please check your internet connection.');
            }
            throw err;
        }
    }

    // ─── Safe Window ───────────────────────────────────────────

    /**
     * Get safe working window from backend rule engine.
     * @param {Object} params - {lat, lon, profile, activity, farmer_name, demo_red}
     * @returns {Promise<Object>} Safe window result with hourly verdicts
     */
    async getSafeWindow({ lat, lon, profile, activity, farmer_name, demo_red = false }) {
        const params = new URLSearchParams({
            lat: String(lat),
            lon: String(lon),
            profile,
            activity,
            farmer_name: farmer_name || 'Farmer',
        });
        if (demo_red) params.append('demo_red', 'true');
        return this._fetch(`/api/safe-window?${params.toString()}`);
    }

    // ─── Weather ───────────────────────────────────────────────

    /**
     * Get current weather data via backend proxy (Open-Meteo).
     * @param {number} lat 
     * @param {number} lon 
     * @returns {Promise<Object>} {temperature, humidity, wind_speed}
     */
    async getCurrentWeather(lat, lon) {
        return this._fetch(`/api/current-weather?lat=${lat}&lon=${lon}`);
    }

    // ─── Alerts ────────────────────────────────────────────────

    /**
     * Create a manual alert (circuit breaker).
     */
    async createAlert({ farmer_name, farmer_id, lat, lon, profile, activity, risk_level, reason }) {
        return this._fetch('/api/alert', {
            method: 'POST',
            body: JSON.stringify({
                farmer_name,
                farmer_id: farmer_id || farmer_name.toLowerCase().replace(/\s+/g, '_'),
                lat, lon, profile, activity,
                risk_level: risk_level || 'RED',
                reason,
            }),
        });
    }

    /**
     * List all alerts, optionally filtered by status.
     */
    async getAlerts(status = null) {
        const url = status ? `/api/alerts?status=${status}` : '/api/alerts';
        return this._fetch(url);
    }

    /**
     * Get pending alerts only.
     */
    async getPendingAlerts() {
        return this._fetch('/api/alerts/pending');
    }

    /**
     * Get a single alert by ID.
     */
    async getAlert(alertId) {
        return this._fetch(`/api/alerts/${alertId}`);
    }

    /**
     * Validate an alert (PENDING_ASHA_REVIEW → VALIDATED).
     */
    async validateAlert(alertId, notes = '') {
        return this._fetch(`/api/alerts/${alertId}/validate`, {
            method: 'PATCH',
            body: JSON.stringify({ notes }),
        });
    }

    /**
     * Reject an alert (PENDING_ASHA_REVIEW → REJECTED).
     */
    async rejectAlert(alertId, notes = '') {
        return this._fetch(`/api/alerts/${alertId}/reject`, {
            method: 'PATCH',
            body: JSON.stringify({ notes }),
        });
    }

    /**
     * Mark farmer as contacted (VALIDATED → FARMER_CONTACTED).
     */
    async contactFarmer(alertId, notes = '') {
        return this._fetch(`/api/alerts/${alertId}/contact`, {
            method: 'PATCH',
            body: JSON.stringify({ notes }),
        });
    }

    /**
     * Resolve an alert (FARMER_CONTACTED → RESOLVED).
     */
    async resolveAlert(alertId, notes = '') {
        return this._fetch(`/api/alerts/${alertId}/resolve`, {
            method: 'PATCH',
            body: JSON.stringify({ notes }),
        });
    }

    // ─── Demo Scenarios ────────────────────────────────────────

    /**
     * Get pre-configured demo scenarios.
     */
    async getDemoScenarios() {
        return this._fetch('/api/demo-scenarios');
    }

    // ─── History ───────────────────────────────────────────────

    /**
     * Save a recommendation to persistent history.
     */
    async saveHistory({ farmer_id, activity, risk_level, safe_window, reason, weather }) {
        return this._fetch('/api/history', {
            method: 'POST',
            body: JSON.stringify({
                farmer_id,
                activity,
                risk_level,
                safe_window: safe_window || '',
                reason: reason || '',
                weather: weather || {},
            }),
        });
    }

    /**
     * Get recommendation history for a farmer.
     */
    async getHistory(farmerId) {
        return this._fetch(`/api/history/${encodeURIComponent(farmerId)}`);
    }

    // ─── Health Check ──────────────────────────────────────────

    /**
     * Check if backend is reachable.
     */
    async healthCheck() {
        return this._fetch('/api/health');
    }
}

// Make available globally and as module
window.JeevanSetuAPI = JeevanSetuAPI;
