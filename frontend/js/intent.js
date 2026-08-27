/**
 * JeevanSetu AI - Deterministic Intent Mapper
 * 
 * Pure keyword-based intent mapping for English, Hindi, and Odia.
 * NO AI/ML — deterministic matching only.
 * 
 * The intent mapper does NOT decide safety.
 * It only identifies the user's requested activity or query type.
 * Safety decisions come from the backend rule engine.
 */

class IntentMapper {
    constructor() {
        // Intent keyword database: intent -> { lang -> [keywords] }
        this.intents = {
            pesticide_spraying: {
                en: ['spray', 'pesticide', 'spraying', 'chemical', 'insecticide', 'fungicide', 'herbicide', 'dawa'],
                hi: ['dawa', 'dawai', 'chhidkaw', 'keetanashak', 'chhidkaav', 'keetnashak', 'spray', 'dawaa'],
                od: ['chhiti', 'bidha', 'kita nashaka', 'kitanashaka', 'chhidka', 'ausadha'],
            },
            general_work: {
                en: ['work', 'field', 'farm', 'harvest', 'crop', 'labor', 'labour', 'plough', 'plow', 'sow', 'weed', 'dig', 'plant'],
                hi: ['kaam', 'khet', 'kheti', 'fasal', 'khetee', 'majdoori', 'jotai', 'buwai', 'katai', 'kam'],
                od: ['kama', 'kheta', 'chasa', 'fasala', 'majaduri', 'halachasa', 'kataiba', 'lagaiba'],
            },
            query_safety: {
                en: ['safe', 'safety', 'risk', 'danger', 'okay', 'dangerous', 'harmful', 'secure', 'unsafe'],
                hi: ['surakshit', 'suraksha', 'khatraa', 'khatarnaak', 'theek', 'haanikarak', 'jokhim', 'khatara'],
                od: ['surakshita', 'bhayanaka', 'khatara', 'khataranaaka', 'theeka', 'haanikaara', 'jokhima'],
            },
            query_window: {
                en: ['window', 'time', 'when', 'hour', 'schedule', 'timing', 'clock', 'morning'],
                hi: ['samay', 'kab', 'kitne baje', 'ghanta', 'subah', 'waqt', 'samaya', 'kab tak'],
                od: ['samaya', 'kebe', 'ghanta', 'sakala', 'bele', 'samaye', 'kete bela'],
            },
        };
    }

    /**
     * Map user text to an intent.
     * 
     * @param {string} text - user's spoken or typed text
     * @param {string} lang - 'en', 'hi', or 'od' (optional, checks all if not provided)
     * @returns {Object} { intent: string|null, confidence: number, matched_keyword: string|null, activity: string|null }
     */
    mapIntent(text, lang = null) {
        if (!text || typeof text !== 'string') {
            return { intent: null, confidence: 0, matched_keyword: null, activity: null };
        }

        const normalizedText = text.toLowerCase().trim();
        const words = normalizedText.split(/\s+/);
        
        let bestMatch = { intent: null, confidence: 0, matched_keyword: null };

        for (const [intent, langKeywords] of Object.entries(this.intents)) {
            // Determine which languages to check
            const langsToCheck = lang ? [lang] : ['en', 'hi', 'od'];

            for (const checkLang of langsToCheck) {
                const keywords = langKeywords[checkLang] || [];

                for (const keyword of keywords) {
                    // Check for exact word match or substring match
                    const keywordLower = keyword.toLowerCase();
                    
                    // Exact word match gets higher confidence
                    if (words.includes(keywordLower)) {
                        if (bestMatch.confidence < 0.9) {
                            bestMatch = { intent, confidence: 0.9, matched_keyword: keyword };
                        }
                    }
                    // Substring match gets lower confidence
                    else if (normalizedText.includes(keywordLower)) {
                        if (bestMatch.confidence < 0.7) {
                            bestMatch = { intent, confidence: 0.7, matched_keyword: keyword };
                        }
                    }
                    // Check if any word starts with the keyword (partial match)
                    else if (words.some(w => w.startsWith(keywordLower.substring(0, 4)) && keywordLower.length >= 4)) {
                        if (bestMatch.confidence < 0.5) {
                            bestMatch = { intent, confidence: 0.5, matched_keyword: keyword };
                        }
                    }
                }
            }
        }

        // Map intent to backend activity parameter
        const activityMap = {
            pesticide_spraying: 'pesticide_spraying',
            general_work: 'general_work',
            query_safety: null,  // Not an activity, it's a query
            query_window: null,  // Not an activity, it's a query
        };

        return {
            intent: bestMatch.intent,
            confidence: bestMatch.confidence,
            matched_keyword: bestMatch.matched_keyword,
            activity: bestMatch.intent ? (activityMap[bestMatch.intent] || null) : null,
        };
    }

    /**
     * Get all supported intents with their keywords for display/help.
     * @param {string} lang 
     * @returns {Array<{intent: string, keywords: string[]}>}
     */
    getSupportedIntents(lang = 'en') {
        return Object.entries(this.intents).map(([intent, langKeywords]) => ({
            intent,
            keywords: langKeywords[lang] || langKeywords['en'],
        }));
    }
}

// Make available globally
window.IntentMapper = IntentMapper;
