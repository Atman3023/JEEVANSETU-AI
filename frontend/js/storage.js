/**
 * JeevanSetu AI - Offline Storage Manager
 * 
 * Uses localStorage for offline-first data persistence.
 * Caches weather, safe window results, profile, consent, and history.
 */

class JeevanSetuStorage {
    constructor() {
        this.KEYS = {
            PROFILE: 'js_profile',
            LANGUAGE: 'js_language',
            CONSENT: 'js_consent',
            LAST_WEATHER: 'js_last_weather',
            LAST_WINDOW: 'js_last_window',
            HISTORY: 'js_history',
        };
        this.MAX_HISTORY = 50;
    }

    // ─── Internal helpers ──────────────────────────────────────

    _save(key, data) {
        try {
            localStorage.setItem(key, JSON.stringify(data));
        } catch (e) {
            console.warn('JeevanSetu Storage: Failed to save', key, e);
        }
    }

    _load(key) {
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            console.warn('JeevanSetu Storage: Failed to load', key, e);
            return null;
        }
    }

    // ─── Profile ───────────────────────────────────────────────

    /**
     * Save farmer profile data.
     * @param {Object} profile - {name, age_group, location, crop, health_profile}
     */
    saveProfile(profile) {
        this._save(this.KEYS.PROFILE, {
            ...profile,
            updated_at: new Date().toISOString(),
        });
    }

    getProfile() {
        return this._load(this.KEYS.PROFILE);
    }

    deleteProfile() {
        localStorage.removeItem(this.KEYS.PROFILE);
    }

    // ─── Language ──────────────────────────────────────────────

    /**
     * Save selected language.
     * @param {string} lang - 'en', 'hi', or 'od'
     */
    saveLanguage(lang) {
        this._save(this.KEYS.LANGUAGE, { lang, updated_at: new Date().toISOString() });
    }

    getLanguage() {
        const data = this._load(this.KEYS.LANGUAGE);
        return data ? data.lang : 'en';
    }

    // ─── Consent ───────────────────────────────────────────────

    /**
     * Save voice consent state.
     * @param {boolean} consented 
     */
    saveConsent(consented) {
        this._save(this.KEYS.CONSENT, {
            consented,
            timestamp: new Date().toISOString(),
        });
    }

    getConsent() {
        const data = this._load(this.KEYS.CONSENT);
        return data ? data.consented : false;
    }

    hasConsented() {
        return this.getConsent() === true;
    }

    // ─── Weather Cache ─────────────────────────────────────────

    /**
     * Cache the latest weather data.
     * @param {Object} weather - {temperature, humidity, wind_speed}
     * @param {Object} location - {lat, lon}
     */
    cacheWeather(weather, location) {
        this._save(this.KEYS.LAST_WEATHER, {
            weather,
            location,
            timestamp: new Date().toISOString(),
        });
    }

    getCachedWeather() {
        return this._load(this.KEYS.LAST_WEATHER);
    }

    // ─── Safe Window Cache ─────────────────────────────────────

    /**
     * Cache the latest safe window result.
     * @param {Object} windowData - full safe-window API response
     */
    cacheWindow(windowData) {
        this._save(this.KEYS.LAST_WINDOW, {
            data: windowData,
            timestamp: new Date().toISOString(),
        });
    }

    getCachedWindow() {
        return this._load(this.KEYS.LAST_WINDOW);
    }

    // ─── History ───────────────────────────────────────────────

    /**
     * Add a recommendation to local history (max 50 entries).
     * @param {Object} entry - {activity, risk_level, safe_window, reason, weather, timestamp}
     */
    addHistory(entry) {
        let history = this._load(this.KEYS.HISTORY) || [];
        history.unshift({
            ...entry,
            timestamp: entry.timestamp || new Date().toISOString(),
        });
        // Keep only the last 50
        if (history.length > this.MAX_HISTORY) {
            history = history.slice(0, this.MAX_HISTORY);
        }
        this._save(this.KEYS.HISTORY, history);
    }

    getHistory() {
        return this._load(this.KEYS.HISTORY) || [];
    }

    // ─── Utility ───────────────────────────────────────────────

    /**
     * Check if the device is currently online.
     */
    isOnline() {
        return navigator.onLine;
    }

    /**
     * Get the timestamp of the last cached window or weather data.
     * @returns {string|null} ISO timestamp or null
     */
    getLastUpdateTimestamp() {
        const window = this.getCachedWindow();
        const weather = this.getCachedWeather();
        const timestamps = [];
        if (window?.timestamp) timestamps.push(window.timestamp);
        if (weather?.timestamp) timestamps.push(weather.timestamp);
        if (timestamps.length === 0) return null;
        timestamps.sort();
        return timestamps[timestamps.length - 1];
    }

    /**
     * Get human-readable time-ago string for last update.
     * @returns {string}
     */
    getTimeSinceUpdate() {
        const ts = this.getLastUpdateTimestamp();
        if (!ts) return '';
        const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
        if (mins < 1) return 'just now';
        if (mins === 1) return '1 minute ago';
        if (mins < 60) return `${mins} minutes ago`;
        const hours = Math.floor(mins / 60);
        if (hours === 1) return '1 hour ago';
        return `${hours} hours ago`;
    }

    /**
     * Clear all JeevanSetu data from localStorage.
     * Used for profile deletion / privacy reset.
     */
    clearAll() {
        Object.values(this.KEYS).forEach(key => {
            localStorage.removeItem(key);
        });
    }
}

// Make available globally
window.JeevanSetuStorage = JeevanSetuStorage;
