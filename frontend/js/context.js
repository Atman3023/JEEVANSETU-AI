/**
 * JeevanSetu AI - Context Engine
 * 
 * Assembles context from farmer profile, health profile, crop, activity,
 * location, weather, and current time into request payloads for the backend.
 * 
 * IMPORTANT: This engine does NOT duplicate rule-engine logic.
 * It only builds the request objects. All safety decisions come from the backend.
 */

class ContextEngine {
    constructor() {
        // Government data provider interfaces (architecture stubs)
        // These define the integration points for future data sources.
        this.providers = {
            weather: {
                current: 'OpenMeteoProvider',  // ACTIVE - via backend
                future: ['IMDProvider'],        // Future: India Meteorological Department
            },
            government: {
                future: [
                    'ICARProvider',   // Future: Indian Council of Agricultural Research
                    'CPCBProvider',   // Future: Central Pollution Control Board
                    'HealthProvider', // Future: eSanjeevani health data
                ],
            },
            soil: {
                demo: 'DemoSoilProvider',  // Demo: static soil data
            },
            inference: {
                future: 'EdgeInferenceService',  // Future: <5MB TFLite model
            },
            prediction: {
                future: 'PredictionService',  // Future: ML prediction layer
            },
        };
    }

    /**
     * Build a request object for the /api/safe-window endpoint.
     * 
     * @param {Object} profile - {name, health_profile, location, ...}
     * @param {string} activity - 'general_work' or 'pesticide_spraying'
     * @param {Object} location - {lat, lon}
     * @param {Object} options - {demo_red: boolean}
     * @returns {Object} Request parameters for the API
     */
    buildRequest(profile, activity, location, options = {}) {
        if (!location || !location.lat || !location.lon) {
            throw new Error('Location is required to check safety.');
        }

        return {
            lat: location.lat,
            lon: location.lon,
            profile: profile?.health_profile || 'healthy_adult',
            activity: activity || 'general_work',
            farmer_name: profile?.name || 'Farmer',
            demo_red: options.demo_red || false,
        };
    }

    /**
     * Build alert context for circuit breaker alert creation.
     * Provides ONLY the information ASHA workers need (privacy: no full health details).
     * 
     * @param {Object} profile - farmer profile
     * @param {Object} result - safe window result from backend
     * @param {Object} weather - current weather data
     * @returns {Object} Alert creation payload
     */
    buildAlertContext(profile, result, weather) {
        const firstRedHour = result?.hourly?.find(h => h.zone === 'RED');

        return {
            farmer_name: profile?.name || 'Farmer',
            farmer_id: (profile?.name || 'farmer').toLowerCase().replace(/\s+/g, '_'),
            lat: result?.location?.lat || 0,
            lon: result?.location?.lon || 0,
            profile: result?.profile || profile?.health_profile || 'healthy_adult',
            activity: result?.activity || 'general_work',
            risk_level: 'RED',
            reason: firstRedHour?.reason || 'Unsafe conditions detected',
        };
    }

    /**
     * Build a history entry for saving a recommendation.
     * 
     * @param {Object} profile - farmer profile
     * @param {Object} result - safe window result from backend
     * @param {Object} weather - current weather data
     * @returns {Object} History save payload
     */
    buildHistoryEntry(profile, result, weather) {
        const farmerId = (profile?.name || 'farmer').toLowerCase().replace(/\s+/g, '_');
        
        // Determine overall risk level
        let riskLevel = 'GREEN';
        if (result?.hourly?.some(h => h.zone === 'RED')) riskLevel = 'RED';
        else if (result?.hourly?.some(h => h.zone === 'YELLOW')) riskLevel = 'YELLOW';

        return {
            farmer_id: farmerId,
            activity: result?.activity || 'general_work',
            risk_level: riskLevel,
            safe_window: result?.window_summary || '',
            reason: result?.hourly?.find(h => h.zone !== 'GREEN')?.reason || 'Within safe thresholds',
            weather: weather || {},
        };
    }

    /**
     * Get time-of-day context.
     * @returns {Object} {hour, period, is_work_hours}
     */
    getTimeContext() {
        const now = new Date();
        const hour = now.getHours();
        let period;
        if (hour >= 5 && hour < 12) period = 'morning';
        else if (hour >= 12 && hour < 17) period = 'afternoon';
        else period = 'evening';

        return {
            hour,
            period,
            is_work_hours: hour >= 5 && hour <= 10,
            timestamp: now.toISOString(),
        };
    }

    /**
     * Get information about available and future data providers.
     * Used for transparency about what's real vs. future.
     * 
     * @returns {Object} Provider status map
     */
    getProviderStatus() {
        return {
            active: [
                { name: 'OpenMeteoProvider', type: 'Weather', status: 'ACTIVE', description: 'Real-time weather via Open-Meteo API' },
            ],
            future: [
                { name: 'IMDProvider', type: 'Weather', status: 'FUTURE', description: 'India Meteorological Department gridded data' },
                { name: 'ICARProvider', type: 'Agricultural', status: 'FUTURE', description: 'ICAR crop-specific safety guidelines' },
                { name: 'CPCBProvider', type: 'Environmental', status: 'FUTURE', description: 'CPCB air quality and pollution data' },
                { name: 'HealthProvider', type: 'Health', status: 'FUTURE', description: 'eSanjeevani health data integration' },
                { name: 'EdgeInferenceService', type: 'AI/ML', status: 'FUTURE', description: '<5MB TFLite model for offline inference' },
                { name: 'PredictionService', type: 'AI/ML', status: 'FUTURE', description: 'ML-based risk prediction layer' },
            ],
            demo: [
                { name: 'DemoSoilProvider', type: 'Soil', status: 'DEMO', description: 'Static demo soil data for prototyping' },
            ],
        };
    }
}

// Make available globally
window.ContextEngine = ContextEngine;
