/**
 * JeevanSetu AI - Voice Input/Output Service
 * 
 * Uses browser Web Speech API for voice recognition and synthesis.
 * Falls back to text input/display when voice is not available.
 * 
 * Future integration point: EdgeInferenceService for <5MB TFLite 
 * offline ASR model. Currently not implemented — architecture is 
 * ready for future integration when a suitable model is available.
 */

// ─── Voice Input Service ───────────────────────────────────────

class VoiceInputService {
    constructor() {
        this.recognition = null;
        this.state = 'idle'; // idle, listening, processing
        this._onStateChange = null;

        // Demo phrase shortcuts for testing without microphone
        this.demoShortcuts = {
            en: [
                { phrase: 'spray pesticide today', label: 'Pesticide spraying query' },
                { phrase: 'is it safe to work', label: 'Safety check' },
                { phrase: 'when can I work', label: 'Safe window query' },
                { phrase: 'general field work', label: 'General work query' },
            ],
            hi: [
                { phrase: 'aaj dawa chhidkaw karna hai', label: 'कीटनाशक छिड़काव' },
                { phrase: 'kya kaam karna surakshit hai', label: 'सुरक्षा जाँच' },
                { phrase: 'kab kaam kar sakta hoon', label: 'सुरक्षित समय' },
                { phrase: 'khet mein kaam karna hai', label: 'सामान्य काम' },
            ],
            od: [
                { phrase: 'aaji chhiti mariba', label: 'କୀଟନାଶକ ଛିଡ଼କାଉ' },
                { phrase: 'kama karibaa surakshita ki', label: 'ସୁରକ୍ଷା ଯାଞ୍ଚ' },
                { phrase: 'kebe kama kariba', label: 'ସୁରକ୍ଷିତ ସମୟ' },
                { phrase: 'kheta re kama', label: 'ସାଧାରଣ କାମ' },
            ],
        };
    }

    /**
     * Check if Web Speech API is available in this browser.
     * @returns {boolean}
     */
    isAvailable() {
        return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    }

    /**
     * Set a callback for state changes.
     * @param {function} callback - receives (state: string)
     */
    onStateChange(callback) {
        this._onStateChange = callback;
    }

    _setState(state) {
        this.state = state;
        if (this._onStateChange) this._onStateChange(state);
    }

    /**
     * Map language code to Web Speech API language tag.
     */
    _getLangTag(lang) {
        const map = { en: 'en-IN', hi: 'hi-IN', od: 'or-IN' };
        return map[lang] || 'en-IN';
    }

    /**
     * Start voice recognition.
     * @param {string} lang - 'en', 'hi', or 'od'
     * @param {function} onResult - callback(transcript: string)
     * @param {function} onError - callback(error: string)
     */
    startListening(lang, onResult, onError) {
        if (!this.isAvailable()) {
            if (onError) onError('Voice input is not supported in this browser. Please use text input.');
            return;
        }

        // Stop any existing recognition
        this.stopListening();

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        this.recognition.lang = this._getLangTag(lang);
        this.recognition.continuous = false;
        this.recognition.interimResults = false;
        this.recognition.maxAlternatives = 1;

        this.recognition.onstart = () => {
            this._setState('listening');
        };

        this.recognition.onresult = (event) => {
            this._setState('processing');
            const transcript = event.results[0][0].transcript;
            if (onResult) onResult(transcript);
            this._setState('idle');
        };

        this.recognition.onerror = (event) => {
            let message = 'Voice recognition error.';
            switch (event.error) {
                case 'no-speech':
                    message = 'No speech detected. Please try again.';
                    break;
                case 'audio-capture':
                    message = 'No microphone found. Please use text input.';
                    break;
                case 'not-allowed':
                    message = 'Microphone permission denied. Please allow microphone access.';
                    break;
                case 'network':
                    message = 'Network error during speech recognition.';
                    break;
            }
            if (onError) onError(message);
            this._setState('idle');
        };

        this.recognition.onend = () => {
            this._setState('idle');
        };

        try {
            this.recognition.start();
        } catch (e) {
            if (onError) onError('Could not start voice recognition.');
            this._setState('idle');
        }
    }

    /**
     * Stop voice recognition.
     */
    stopListening() {
        if (this.recognition) {
            try {
                this.recognition.stop();
            } catch (e) {
                // Ignore errors on stop
            }
            this.recognition = null;
        }
        this._setState('idle');
    }

    /**
     * Get demo phrase shortcuts for the given language.
     * @param {string} lang 
     * @returns {Array<{phrase: string, label: string}>}
     */
    getDemoShortcuts(lang) {
        return this.demoShortcuts[lang] || this.demoShortcuts['en'];
    }
}


// ─── Voice Output Service ──────────────────────────────────────

class VoiceOutputService {
    constructor() {
        this.synth = window.speechSynthesis || null;
    }

    /**
     * Check if speech synthesis is available.
     * @returns {boolean}
     */
    isAvailable() {
        return !!this.synth;
    }

    /**
     * Speak text aloud.
     * @param {string} text - text to speak
     * @param {string} lang - 'en', 'hi', or 'od'
     */
    speak(text, lang = 'en') {
        if (!this.isAvailable()) {
            console.warn('Speech synthesis not available.');
            return;
        }

        this.stop();

        const utterance = new SpeechSynthesisUtterance(text);

        // Try to find a matching voice
        const langMap = { en: 'en', hi: 'hi', od: 'or' };
        const targetLang = langMap[lang] || 'en';
        const voices = this.synth.getVoices();
        const matchingVoice = voices.find(v => v.lang.startsWith(targetLang));
        if (matchingVoice) {
            utterance.voice = matchingVoice;
        }

        utterance.rate = 0.9;
        utterance.pitch = 1;

        this.synth.speak(utterance);
    }

    /**
     * Stop any current speech.
     */
    stop() {
        if (this.isAvailable()) {
            this.synth.cancel();
        }
    }
}

// Make available globally
window.VoiceInputService = VoiceInputService;
window.VoiceOutputService = VoiceOutputService;
