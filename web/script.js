//=============================================================================
// Syntax Prime V2 - Chat Interface JavaScript (MERGED WORKING VERSION + GOOGLE TRENDS)
// Combines fixes from both versions with proper anti-duplication + Google Trends Training
// Date: 9/27/25 - Working sidebar + submit protection + Google Trends Integration
// Date: 9/28/25 - Added Voice Synthesis & Image Generation Integration
//=============================================================================

class SyntaxPrimeChat {
    constructor() {
        this.apiBase = window.location.origin;
        this.currentThreadId = null;
        this.currentPersonality = 'syntaxprime';
        this.uploadedFiles = [];
        this.isTyping = false;
        this.bookmarkToCreate = null;
        
        // Enhanced anti-duplication protection
        this.isSubmitting = false;
        this.lastSubmitTime = 0;
        this.lastMessage = '';
        this.submitCooldown = 1000;
        this.messageDuplicationWindow = 5000;

        // Google Trends Training System
        this.trendsEnabled = false;
        this.pendingOpportunities = [];
        this.trainingStats = {
            total_feedback: 0,
            good_matches: 0,
            bad_matches: 0,
            accuracy: 0
        };
        this.trendsPollingInterval = null;

        // Voice Synthesis System - Date: 9/28/25
        this.voiceEnabled = false;
        this.currentAudio = null;
        this.audioCache = new Map();
        this.voicePersonalities = {
            'syntaxprime': 'adam',
            'syntaxbot': 'josh',
            'nil.exe': 'onyx',
            'ggpt': 'echo'
        };

        // Image Generation System - Date: 9/28/25
        this.imageEnabled = false;
        this.imageGenerationQueue = [];
        this.currentImageGeneration = null;

        this.init();
    }

    // === Initialization ===
    init() {
        this.setupEventListeners();
        this.loadPersonalities();
        this.loadConversations();
        this.setupDragAndDrop();
        this.autoResizeTextarea();
        this.initializeTrendsSystem();
        this.initializeVoiceSystem(); // Date: 9/28/25
        this.initializeImageSystem(); // Date: 9/28/25

        // Focus message input
        document.getElementById('messageInput').focus();
        
        this.debugDatetimeContext();
    }

    debugDatetimeContext() {
        const now = new Date();
        console.log('🕐 Frontend Datetime Context:');
        console.log('  Current Date:', now.toISOString().split('T')[0]);
        console.log('  Current Time:', now.toLocaleTimeString('en-US', { hour12: false }));
        console.log('  Timezone:', Intl.DateTimeFormat().resolvedOptions().timeZone);
        console.log('  Full ISO:', now.toISOString());
    }

    setupEventListeners() {
        // ENHANCED: Check for existing listeners to prevent duplicates
        console.log('🔧 Setting up event listeners...');
        
        // Remove any existing listeners first
        const elements = [
            'sidebarToggle', 'newChatBtn', 'settingsBtn', 'logoutBtn',
            'personalitySelect', 'messageInput', 'sendButton', 'fileButton', 'fileInput', 'rememberBtn', 'trendsBtn'
        ];
        
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element && element._syntaxListenersAttached) {
                console.log(`⚠️ Listeners already attached to ${id}, skipping`);
                return;
            }
        });

        // Header controls
        const sidebarToggle = document.getElementById('sidebarToggle');
        if (sidebarToggle && !sidebarToggle._syntaxListenersAttached) {
            sidebarToggle.addEventListener('click', this.toggleSidebar.bind(this));
            sidebarToggle._syntaxListenersAttached = true;
        }

        const newChatBtn = document.getElementById('newChatBtn');
        if (newChatBtn && !newChatBtn._syntaxListenersAttached) {
            newChatBtn.addEventListener('click', this.startNewChat.bind(this));
            newChatBtn._syntaxListenersAttached = true;
        }

        const settingsBtn = document.getElementById('settingsBtn');
        if (settingsBtn && !settingsBtn._syntaxListenersAttached) {
            settingsBtn.addEventListener('click', this.openSettings.bind(this));
            settingsBtn._syntaxListenersAttached = true;
        }

        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn && !logoutBtn._syntaxListenersAttached) {
            logoutBtn.addEventListener('click', this.logout.bind(this));
            logoutBtn._syntaxListenersAttached = true;
        }

        // Personality selector
        const personalitySelect = document.getElementById('personalitySelect');
        if (personalitySelect && !personalitySelect._syntaxListenersAttached) {
            personalitySelect.addEventListener('change', (e) => {
                this.currentPersonality = e.target.value;
                this.saveSettings();
            });
            personalitySelect._syntaxListenersAttached = true;
        }

        // Chat input with enhanced anti-duplication
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');

        if (messageInput && !messageInput._syntaxListenersAttached) {
            messageInput.addEventListener('input', this.handleInputChange.bind(this));
            messageInput.addEventListener('keydown', this.handleKeyPress.bind(this));
            messageInput._syntaxListenersAttached = true;
        }
        
        // CRITICAL: Ensure only ONE click listener on send button - PROTECTED
        if (sendButton && !sendButton._syntaxListenersAttached) {
            console.log('🔧 Attaching click listener to send button - PROTECTED');
            sendButton.addEventListener('click', this.handleSendClick.bind(this));
            sendButton._syntaxListenersAttached = true;
        } else if (sendButton) {
            console.log('⚠️ Send button already has listeners attached');
        }

        // File upload - FIXED: Correct element IDs
        const fileButton = document.getElementById('fileButton');
        const fileInput = document.getElementById('fileInput');
        
        if (fileButton && fileInput && !fileButton._syntaxListenersAttached) {
            fileButton.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', this.handleFileSelect.bind(this));
            fileButton._syntaxListenersAttached = true;
            fileInput._syntaxListenersAttached = true;
        }

        // Remember button
        const rememberBtn = document.getElementById('rememberBtn');
        if (rememberBtn && !rememberBtn._syntaxListenersAttached) {
            rememberBtn.addEventListener('click', this.showBookmarkModal.bind(this));
            rememberBtn._syntaxListenersAttached = true;
        }

        // Google Trends Training Button
        const trendsBtn = document.getElementById('trendsBtn');
        if (trendsBtn && !trendsBtn._syntaxListenersAttached) {
            trendsBtn.addEventListener('click', this.showTrendsOpportunities.bind(this));
            trendsBtn._syntaxListenersAttached = true;
        }

        // Modal handlers
        this.setupModalHandlers();
        
        console.log('✅ Event listeners setup complete');
    }

    // ENHANCED: Anti-duplication send handler with detailed logging - PROTECTED
    handleSendClick(event) {
        console.log('🖱️ handleSendClick called');
        event.preventDefault();
        event.stopPropagation();

        // Anti-duplication protection with detailed logging
        const now = Date.now();
        const timeSinceLastSubmit = now - this.lastSubmitTime;
        
        console.log('🔍 Submit check:', {
            isSubmitting: this.isSubmitting,
            timeSinceLastSubmit,
            cooldownRequired: 1000
        });

        if (this.isSubmitting) {
            console.log('⛔️ BLOCKED: Already submitting');
            return;
        }
        
        if (timeSinceLastSubmit < 1000) {
            console.log('⛔️ BLOCKED: Within cooldown period');
            return;
        }

        console.log('✅ Proceeding with sendMessage()');
        this.sendMessage();
    }

    handleKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            event.stopPropagation();

            const now = Date.now();
            if (this.isSubmitting || (now - this.lastSubmitTime) < 1000) {
                console.log('⛔️ Double submission prevented (Enter key)');
                return;
            }

            if (!document.getElementById('sendButton').disabled && !this.isTyping) {
                this.sendMessage();
            }
        }
    }

    setupModalHandlers() {
        // Bookmark modal
        const bookmarkModal = document.getElementById('bookmarkModal');
        const closeBookmarkModal = document.getElementById('closeBookmarkModal');
        const cancelBookmark = document.getElementById('cancelBookmark');
        const saveBookmark = document.getElementById('saveBookmark');

        if (closeBookmarkModal) closeBookmarkModal.addEventListener('click', () => this.hideModal(bookmarkModal));
        if (cancelBookmark) cancelBookmark.addEventListener('click', () => this.hideModal(bookmarkModal));
        if (saveBookmark) saveBookmark.addEventListener('click', this.saveBookmark.bind(this));

        // Settings modal
        const settingsModal = document.getElementById('settingsModal');
        const closeSettingsModal = document.getElementById('closeSettingsModal');
        const saveSettingsBtn = document.getElementById('saveSettings');

        if (closeSettingsModal) closeSettingsModal.addEventListener('click', () => this.hideModal(settingsModal));
        if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', this.saveSettings.bind(this));

        // Close modals on outside click
        [bookmarkModal, settingsModal].forEach(modal => {
            if (modal) {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        this.hideModal(modal);
                    }
                });
            }
        });
    }

    // === Voice Synthesis Integration - Date: 9/28/25 ===
    async initializeVoiceSystem() {
        try {
            console.log('🎤 Initializing Voice Synthesis system...');
            
            // Check if voice system is available
            const healthCheck = await this.apiCall('/api/voice/health', 'GET');
            
            if (healthCheck && healthCheck.status === 'healthy') {
                this.voiceEnabled = true;
                console.log('✅ Voice Synthesis system available');
                
                // Load voice personality mappings
                await this.loadVoicePersonalities();
            } else {
                console.log('⚠️ Voice Synthesis system not available');
            }
        } catch (error) {
            console.log('⚠️ Voice Synthesis system not available:', error.message);
            this.voiceEnabled = false;
        }
    }

    async loadVoicePersonalities() {
        try {
            const personalities = await this.apiCall('/api/voice/personalities', 'GET');
            if (personalities) {
                this.voicePersonalities = { ...this.voicePersonalities, ...personalities };
                console.log('🎭 Voice personalities loaded:', this.voicePersonalities);
            }
        } catch (error) {
            console.error('Error loading voice personalities:', error);
        }
    }

    async synthesizeVoice(text, messageId) {
        if (!this.voiceEnabled) return null;

        try {
            console.log(`🎤 Synthesizing voice for message ${messageId}`);
            
            const voiceModel = this.voicePersonalities[this.currentPersonality] || 'adam';
            
            const response = await this.apiCall('/api/voice/synthesize', 'POST', {
                text: text,
                voice: voiceModel,
                message_id: messageId
            });

            if (response && response.audio_url) {
                // Cache the audio URL
                this.audioCache.set(messageId, response.audio_url);
                console.log(`✅ Voice synthesized for message ${messageId}`);
                return response.audio_url;
            }
        } catch (error) {
            console.error('Voice synthesis failed:', error);
        }
        return null;
    }

    async playVoiceMessage(messageId, speakerButton) {
        if (!this.voiceEnabled) return;

        try {
            // Stop any currently playing audio
            if (this.currentAudio) {
                this.currentAudio.pause();
                this.currentAudio = null;
                this.clearPlayingStates();
            }

            // Set loading state
            speakerButton.classList.add('loading');
            speakerButton.innerHTML = '🔄';

            // Check cache first
            let audioUrl = this.audioCache.get(messageId);
            
            if (!audioUrl) {
                // Try to fetch from API
                const response = await this.apiCall(`/api/voice/audio/${messageId}`, 'GET');
                if (response && response.audio_url) {
                    audioUrl = response.audio_url;
                    this.audioCache.set(messageId, audioUrl);
                }
            }

            if (!audioUrl) {
                throw new Error('Audio not available');
            }

            // Create and play audio
            const audio = new Audio(audioUrl);
            this.currentAudio = audio;

            // Set playing state
            speakerButton.classList.remove('loading');
            speakerButton.classList.add('playing');
            speakerButton.innerHTML = '🔊';

            // Add waveform animation
            this.showWaveformAnimation(speakerButton);

            // Audio event handlers
            audio.onended = () => {
                this.clearPlayingStates();
                this.hideWaveformAnimation(speakerButton);
                speakerButton.innerHTML = '🔊';
            };

            audio.onerror = () => {
                console.error('Audio playback failed');
                this.clearPlayingStates();
                this.hideWaveformAnimation(speakerButton);
                speakerButton.innerHTML = '🔊';
                speakerButton.classList.remove('loading', 'playing');
            };

            await audio.play();
            console.log(`🔊 Playing voice for message ${messageId}`);

        } catch (error) {
            console.error('Voice playback failed:', error);
            speakerButton.classList.remove('loading', 'playing');
            speakerButton.innerHTML = '🔊';
        }
    }

    clearPlayingStates() {
        const playingButtons = document.querySelectorAll('.speaker-button.playing');
        playingButtons.forEach(btn => {
            btn.classList.remove('playing');
            this.hideWaveformAnimation(btn);
        });
    }

    showRememberButton(messageId) {
        const rememberBtn = document.getElementById('rememberBtn');
        if (rememberBtn) {
            rememberBtn.style.display = 'block';
            rememberBtn.setAttribute('data-message-id', messageId);
        }
    }

    showError(message) {
        console.error('Error:', message);
        // Could add a toast notification here
    }
}

// ENHANCED: Proper initialization with DOM ready protection - PROTECTED
let syntaxChat = null;

function initializeSyntaxChat() {
    if (syntaxChat) {
        console.log('⛔️ SyntaxChat already initialized, skipping');
        return;
    }

    console.log('🚀 Initializing SyntaxChat');
    try {
        syntaxChat = new SyntaxPrimeChat();
        window.syntaxPrimeChat = syntaxChat; // Global reference for onclick handlers
        console.log('✅ SyntaxChat initialized successfully');
    } catch (error) {
        console.error('❌ Failed to initialize chat:', error);
    }
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSyntaxChat);
} else {
    // DOM is already ready
    initializeSyntaxChat();
}

// Add notification animations and Google Trends styling + Voice & Image Integration - Date: 9/28/25
const style = document.createElement('style');
style.textContent = `
@keyframes slideInRight {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
@keyframes slideOutRight {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(100%); opacity: 0; }
}

/* Google Trends Training Styles */
.trends-opportunity {
    border-left: 4px solid #4CAF50;
}

.trends-header {
    border-left: 4px solid #2196F3;
}

.trends-info {
    border-left: 4px solid #FF9800;
}

.trends-error {
    border-left: 4px solid #f44336;
}

.trends-bubble {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}

.opportunity-card {
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    padding: 16px;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    color: #333;
}

.opportunity-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.opportunity-keyword {
    font-size: 18px;
    font-weight: bold;
    color: #2c3e50;
}

.opportunity-meta {
    display: flex;
    gap: 8px;
    align-items: center;
}

.business-area {
    background: #3498db;
    color: white;
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
}

.urgency-level {
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
}

.urgency-level.critical {
    background: #e74c3c;
    color: white;
}

.urgency-level.high {
    background: #f39c12;
    color: white;
}

.urgency-level.medium {
    background: #f1c40f;
    color: #333;
}

.urgency-level.low {
    background: #95a5a6;
    color: white;
}

.opportunity-details {
    margin-bottom: 16px;
}

.opportunity-stats {
    display: flex;
    gap: 16px;
    margin-bottom: 8px;
    font-size: 14px;
    color: #666;
}

.opportunity-description {
    color: #555;
    line-height: 1.4;
}

.opportunity-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
}

.training-btn {
    flex: 1;
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 14px;
}

.training-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

.training-btn:disabled {
    cursor: not-allowed;
}

.good-match {
    background: #27ae60;
    color: white;
}

.good-match:hover:not(:disabled) {
    background: #219a52;
}

.bad-match {
    background: #e74c3c;
    color: white;
}

.bad-match:hover:not(:disabled) {
    background: #c0392b;
}

.feedback-success {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px;
    background: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 8px;
    color: #155724;
}

.success-icon {
    font-size: 18px;
}

.success-text {
    font-weight: 500;
}

/* Toast Notifications */
.syntax-toast {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 10000;
    max-width: 400px;
    transform: translateX(100%);
    opacity: 0;
    transition: all 0.3s ease;
}

.syntax-toast.toast-show {
    transform: translateX(0);
    opacity: 1;
}

.toast-content {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    background: white;
    border-left: 4px solid #ccc;
}

.toast-info .toast-content {
    border-left-color: #2196F3;
}

.toast-success .toast-content {
    border-left-color: #4CAF50;
}

.toast-error .toast-content {
    border-left-color: #f44336;
}

.toast-warning .toast-content {
    border-left-color: #FF9800;
}

.toast-message {
    flex: 1;
    margin-right: 12px;
    font-size: 14px;
    line-height: 1.4;
}

.toast-close {
    background: none;
    border: none;
    font-size: 18px;
    cursor: pointer;
    color: #666;
    padding: 0;
    line-height: 1;
}

.toast-close:hover {
    color: #333;
}
`;
document.head.appendChild(style);showWaveformAnimation(speakerButton) {
        // Remove existing waveform
        this.hideWaveformAnimation(speakerButton);
        
        const waveform = document.createElement('div');
        waveform.className = 'waveform-animation';
        waveform.innerHTML = `
            <div class="waveform-bar"></div>
            <div class="waveform-bar"></div>
            <div class="waveform-bar"></div>
            <div class="waveform-bar"></div>
            <div class="waveform-bar"></div>
        `;
        
        speakerButton.parentNode.appendChild(waveform);
    }

    hideWaveformAnimation(speakerButton) {
        const waveform = speakerButton.parentNode.querySelector('.waveform-animation');
        if (waveform) {
            waveform.remove();
        }
    }

    // === Image Generation Integration - Date: 9/28/25 ===
    async initializeImageSystem() {
        try {
            console.log('🎨 Initializing Image Generation system...');
            
            // Check if image system is available
            const healthCheck = await this.apiCall('/integrations/image-generation/health', 'GET');
            
            if (healthCheck && healthCheck.status === 'healthy') {
                this.imageEnabled = true;
                console.log('✅ Image Generation system available');
            } else {
                console.log('⚠️ Image Generation system not available');
            }
        } catch (error) {
            console.log('⚠️ Image Generation system not available:', error.message);
            this.imageEnabled = false;
        }
    }

    detectImageCommands(message) {
        const imagePatterns = [
            /^image\s+(.+)/i,
            /^mockup\s+(.+)/i
        ];
        
        for (const pattern of imagePatterns) {
            const match = message.match(pattern);
            if (match) {
                return match[1].trim(); // Return the prompt
            }
        }
        return null;
    }

    async generateImage(prompt, messageElement) {
        if (!this.imageEnabled) return;

        try {
            console.log(`🎨 Generating image for prompt: "${prompt}"`);
            
            // Show progress indicator
            const progressElement = this.showImageProgress(messageElement, prompt);
            
            const response = await this.apiCall('/integrations/image-generation/generate', 'POST', {
                prompt: prompt,
                format: 'png',
                size: '512x512'
            });

            if (response && response.image_data) {
                // Hide progress indicator
                if (progressElement) {
                    progressElement.remove();
                }
                
                // Display the generated image
                this.displayGeneratedImage(messageElement, response, prompt);
                console.log('✅ Image generated and displayed');
            } else {
                throw new Error('No image data received');
            }

        } catch (error) {
            console.error('Image generation failed:', error);
            
            // Hide progress and show error
            const progressElement = messageElement.querySelector('.image-generation-progress');
            if (progressElement) {
                progressElement.remove();
            }
            
            this.showImageError(messageElement, 'Image generation failed. Please try again.');
        }
    }

    showImageProgress(messageElement, prompt) {
        const progressDiv = document.createElement('div');
        progressDiv.className = 'image-generation-progress';
        progressDiv.innerHTML = `
            <div class="progress-spinner"></div>
            <div class="progress-info">
                <div class="progress-title">Generating image...</div>
                <div class="progress-subtitle">"${prompt.length > 50 ? prompt.substring(0, 50) + '...' : prompt}"</div>
                <div class="progress-bar-container">
                    <div class="progress-bar" style="width: 0%"></div>
                </div>
            </div>
        `;
        
        const messageBubble = messageElement.querySelector('.message-bubble');
        messageBubble.appendChild(progressDiv);
        
        // Animate progress bar
        const progressBar = progressDiv.querySelector('.progress-bar');
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += Math.random() * 15;
            if (progress > 90) progress = 90;
            progressBar.style.width = `${progress}%`;
        }, 500);
        
        progressDiv._progressInterval = progressInterval;
        return progressDiv;
    }

    displayGeneratedImage(messageElement, imageData, prompt) {
        const imageContainer = document.createElement('div');
        imageContainer.className = 'generated-image-container';
        
        const img = document.createElement('img');
        img.className = 'generated-image';
        img.src = `data:image/png;base64,${imageData.image_data}`;
        img.alt = prompt;
        
        const controls = document.createElement('div');
        controls.className = 'image-controls';
        controls.innerHTML = `
            <div class="image-info">
                <div class="image-prompt">${prompt}</div>
                <div class="image-metadata">Generated • PNG • 512x512</div>
            </div>
            <button class="download-button" onclick="window.syntaxPrimeChat.downloadImage('${imageData.image_data}', '${prompt}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7,10 12,15 17,10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Download PNG
            </button>
        `;
        
        imageContainer.appendChild(img);
        imageContainer.appendChild(controls);
        
        const messageBubble = messageElement.querySelector('.message-bubble');
        messageBubble.appendChild(imageContainer);
        
        // Scroll to show new image
        messageElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    showImageError(messageElement, errorMessage) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'image-generation-error';
        errorDiv.innerHTML = `
            <div style="color: var(--error); padding: var(--spacing-md); background: rgba(239, 68, 68, 0.1); border-radius: var(--radius-md); margin-top: var(--spacing-sm);">
                ❌ ${errorMessage}
            </div>
        `;
        
        const messageBubble = messageElement.querySelector('.message-bubble');
        messageBubble.appendChild(errorDiv);
    }

    downloadImage(imageData, prompt) {
        try {
            const link = document.createElement('a');
            link.href = `data:image/png;base64,${imageData}`;
            link.download = `${prompt.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50)}.png`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            console.log('📥 Image downloaded');
        } catch (error) {
            console.error('Download failed:', error);
        }
    }

    // === Message detection for trends keywords ===
    detectTrendsKeywords(message) {
        const trendsKeywords = [
            "trends", "google trends", "opportunities", "trending",
            "trend analysis", "search trends", "opportunity detection"
        ];
        
        const messageLower = message.toLowerCase();
        return trendsKeywords.some(keyword => messageLower.includes(keyword));
    }

    // === Google Trends Training System ===
    async initializeTrendsSystem() {
        try {
            console.log('📊 Initializing Google Trends system...');
            
            // Check if trends system is available
            const healthCheck = await this.apiCall('/api/health/trends', 'GET');
            
            if (healthCheck && healthCheck.status === 'healthy') {
                this.trendsEnabled = true;
                console.log('✅ Google Trends system available');
                
                // Load initial training stats
                await this.loadTrainingStats();
                
                // Set up periodic polling for new opportunities (every 30 seconds)
                this.setupTrendsPolling();
            } else {
                console.log('⚠️ Google Trends system not available');
            }
        } catch (error) {
            console.log('⚠️ Google Trends system not available:', error.message);
            this.trendsEnabled = false;
        }
    }

    setupTrendsPolling() {
        if (this.trendsPollingInterval) {
            clearInterval(this.trendsPollingInterval);
        }
        
        this.trendsPollingInterval = setInterval(async () => {
            try {
                await this.checkForNewOpportunities();
            } catch (error) {
                console.error('Trends polling error:', error);
            }
        }, 30000); // Check every 30 seconds
    }

    async checkForNewOpportunities() {
        if (!this.trendsEnabled) return;
        
        try {
            const opportunities = await this.apiCall('/api/trends/opportunities', 'GET');
            
            if (opportunities && opportunities.length > 0) {
                const newOpportunities = opportunities.filter(opp =>
                    !this.pendingOpportunities.some(pending => pending.id === opp.id)
                );
                
                if (newOpportunities.length > 0) {
                    console.log(`📈 ${newOpportunities.length} new trend opportunities found`);
                    
                    // Add to pending list
                    this.pendingOpportunities.push(...newOpportunities);
                    
                    // Show browser notification
                    this.showBrowserNotification(
                        'New Trend Opportunities',
                        `${newOpportunities.length} new training opportunities available`
                    );
                    
                    // Show in-app toast
                    this.showToast(
                        `📈 ${newOpportunities.length} new trend opportunities available`,
                        'info'
                    );
                }
            }
        } catch (error) {
            console.error('Error checking for new opportunities:', error);
        }
    }

    async loadTrainingStats() {
        try {
            const stats = await this.apiCall('/api/trends/status', 'GET');
            if (stats) {
                this.trainingStats = {
                    total_feedback: stats.total_feedback || 0,
                    good_matches: stats.good_matches || 0,
                    bad_matches: stats.bad_matches || 0,
                    accuracy: stats.accuracy || 0
                };
                console.log('📊 Training stats loaded:', this.trainingStats);
            }
        } catch (error) {
            console.error('Error loading training stats:', error);
        }
    }

    async showTrendsOpportunities() {
        if (!this.trendsEnabled) {
            this.showToast('❌ Google Trends system not available', 'error');
            return;
        }

        try {
            console.log('📊 Loading trend opportunities...');
            
            // Fetch latest opportunities
            const opportunities = await this.apiCall('/api/trends/opportunities', 'GET');
            
            if (!opportunities || opportunities.length === 0) {
                this.addTrendsMessage('No trend opportunities available for training at the moment.', 'info');
                return;
            }

            // Display opportunities as special chat messages
            this.addTrendsMessage(
                `Found ${opportunities.length} trend opportunities for training:`,
                'header'
            );

            // Show each opportunity as a card
            opportunities.forEach(opportunity => {
                this.addTrendsOpportunityCard(opportunity);
            });

            // Update pending opportunities
            this.pendingOpportunities = opportunities;

        } catch (error) {
            console.error('Error loading trends opportunities:', error);
            this.addTrendsMessage('❌ Error loading trend opportunities. Please try again.', 'error');
        }
    }

    addTrendsMessage(content, type = 'info') {
        const messagesContainer = document.getElementById('chatMessages');
        const welcomeMessage = messagesContainer.querySelector('.welcome-message');

        // Remove welcome message on first interaction
        if (welcomeMessage) {
            welcomeMessage.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message assistant trends-${type}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = '📊';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble trends-bubble';

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.innerHTML = content;

        bubble.appendChild(textDiv);
        contentDiv.appendChild(bubble);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    addTrendsOpportunityCard(opportunity) {
        const messagesContainer = document.getElementById('chatMessages');
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant trends-opportunity';
        messageDiv.dataset.opportunityId = opportunity.id;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = this.getUrgencyIcon(opportunity.urgency_level);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble opportunity-card';

        // Opportunity details
        const headerDiv = document.createElement('div');
        headerDiv.className = 'opportunity-header';
        headerDiv.innerHTML = `
            <div class="opportunity-keyword">${opportunity.keyword}</div>
            <div class="opportunity-meta">
                <span class="business-area">${opportunity.business_area}</span>
                <span class="urgency-level ${opportunity.urgency_level}">${opportunity.urgency_level}</span>
            </div>
        `;

        const detailsDiv = document.createElement('div');
        detailsDiv.className = 'opportunity-details';
        detailsDiv.innerHTML = `
            <div class="opportunity-stats">
                <span>📈 Trend Score: ${opportunity.trend_score}</span>
                <span>⏰ Time Left: ${opportunity.time_left}</span>
            </div>
            <div class="opportunity-description">
                <strong>${opportunity.opportunity_type}</strong> opportunity detected for keyword analysis
            </div>
        `;

        // Training buttons
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'opportunity-actions';

        const goodBtn = document.createElement('button');
        goodBtn.className = 'training-btn good-match';
        goodBtn.innerHTML = '✅ Good Match';
        goodBtn.addEventListener('click', () => this.submitTrainingFeedback(opportunity.id, 'good_match'));

        const badBtn = document.createElement('button');
        badBtn.className = 'training-btn bad-match';
        badBtn.innerHTML = '❌ Bad Match';
        badBtn.addEventListener('click', () => this.submitTrainingFeedback(opportunity.id, 'bad_match'));

        actionsDiv.appendChild(goodBtn);
        actionsDiv.appendChild(badBtn);

        bubble.appendChild(headerDiv);
        bubble.appendChild(detailsDiv);
        bubble.appendChild(actionsDiv);

        contentDiv.appendChild(bubble);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    getUrgencyIcon(urgency) {
        const icons = {
            'critical': '🚨',
            'high': '🔥',
            'medium': '⚡',
            'low': '💡'
        };
        return icons[urgency] || '📊';
    }

    async submitTrainingFeedback(opportunityId, feedbackType) {
        try {
            console.log(`📤 Submitting ${feedbackType} feedback for opportunity ${opportunityId}`);

            // Find the opportunity card
            const opportunityCard = document.querySelector(`[data-opportunity-id="${opportunityId}"]`);
            if (!opportunityCard) return;

            // Disable buttons during submission
            const buttons = opportunityCard.querySelectorAll('.training-btn');
            buttons.forEach(btn => {
                btn.disabled = true;
                btn.style.opacity = '0.6';
            });

            // Submit feedback to API
            const response = await this.apiCall('/api/trends/feedback', 'POST', {
                opportunity_id: opportunityId,
                feedback_type: feedbackType,
                timestamp: new Date().toISOString()
            });

            if (response && response.success) {
                // Show success feedback
                this.showTrainingSuccess(opportunityCard, feedbackType);
                
                // Update training stats
                await this.loadTrainingStats();
                
                // Remove from pending opportunities
                this.pendingOpportunities = this.pendingOpportunities.filter(
                    opp => opp.id !== opportunityId
                );

                // Show success toast
                this.showToast(
                    `✅ ${feedbackType === 'good_match' ? 'Good' : 'Bad'} match feedback recorded`,
                    'success'
                );

                // Remove the opportunity card after 2 seconds
                setTimeout(() => {
                    opportunityCard.style.transition = 'opacity 0.5s ease-out';
                    opportunityCard.style.opacity = '0';
                    setTimeout(() => {
                        if (opportunityCard.parentNode) {
                            opportunityCard.parentNode.removeChild(opportunityCard);
                        }
                    }, 500);
                }, 2000);

            } else {
                throw new Error(response?.error || 'Failed to submit feedback');
            }

        } catch (error) {
            console.error('Error submitting training feedback:', error);
            
            // Re-enable buttons
            const opportunityCard = document.querySelector(`[data-opportunity-id="${opportunityId}"]`);
            if (opportunityCard) {
                const buttons = opportunityCard.querySelectorAll('.training-btn');
                buttons.forEach(btn => {
                    btn.disabled = false;
                    btn.style.opacity = '1';
                });
            }

            this.showToast('❌ Error submitting feedback. Please try again.', 'error');
        }
    }

    showTrainingSuccess(opportunityCard, feedbackType) {
        const actionsDiv = opportunityCard.querySelector('.opportunity-actions');
        if (actionsDiv) {
            actionsDiv.innerHTML = `
                <div class="feedback-success">
                    <span class="success-icon">${feedbackType === 'good_match' ? '✅' : '❌'}</span>
                    <span class="success-text">Feedback recorded!</span>
                </div>
            `;
        }
    }

    // === Notification Systems ===
    showBrowserNotification(title, body) {
        if ('Notification' in window) {
            if (Notification.permission === 'granted') {
                new Notification(title, {
                    body: body,
                    icon: 'static/syntax-buffering.png',
                    tag: 'syntax-trends',
                    requireInteraction: false
                });
            } else if (Notification.permission !== 'denied') {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        new Notification(title, {
                            body: body,
                            icon: 'static/syntax-buffering.png',
                            tag: 'syntax-trends'
                        });
                    }
                });
            }
        }
    }

    showToast(message, type = 'info') {
        // Remove any existing toasts
        const existingToast = document.querySelector('.syntax-toast');
        if (existingToast) {
            existingToast.remove();
        }

        const toast = document.createElement('div');
        toast.className = `syntax-toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-message">${message}</span>
                <button class="toast-close" onclick="this.parentNode.parentNode.remove()">×</button>
            </div>
        `;

        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.classList.add('toast-show');
        }, 100);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.remove('toast-show');
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.remove();
                    }
                }, 300);
            }
        }, 5000);
    }

    // ENHANCED: API call from working version with better error handling
    async apiCall(endpoint, method = 'GET', data = null) {
        try {
            const options = {
                method,
                headers: {},
                credentials: 'include'
            };

            if (data && method !== 'GET') {
                if (data instanceof FormData) {
                    options.body = data;
                } else {
                    options.headers['Content-Type'] = 'application/json';
                    options.body = JSON.stringify(data);
                }
            }

            const response = await fetch(`${this.apiBase}${endpoint}`, options);

            if (response.status === 401) {
                this.logout();
                return;
            }

            // Parse response
            let responseData;
            const contentType = response.headers.get('content-type');

            if (contentType && contentType.includes('application/json')) {
                responseData = await response.json();
            } else {
                responseData = await response.text();
            }

            if (!response.ok) {
                let errorMessage = 'Unknown error';

                if (typeof responseData === 'object' && responseData.detail) {
                    if (Array.isArray(responseData.detail)) {
                        errorMessage = responseData.detail.map(err => `${err.loc?.join('.')}: ${err.msg}`).join(', ');
                    } else {
                        errorMessage = responseData.detail;
                    }
                } else if (typeof responseData === 'string') {
                    errorMessage = responseData;
                } else if (typeof responseData === 'object' && responseData.message) {
                    errorMessage = responseData.message;
                }

                throw new Error(`HTTP ${response.status}: ${errorMessage}`);
            }

            return responseData;

        } catch (error) {
            console.error('API call failed:', error);

            let displayMessage = error.message;
            if (error.message.includes('Failed to fetch')) {
                displayMessage = 'Connection error. Please check your internet connection.';
            } else if (error.message.includes('422')) {
                displayMessage = 'Invalid request format. Please try again.';
            }

            this.showError(displayMessage);
            throw error;
        }
    }

    // ENHANCED: Send message with detailed duplication tracking and trends detection - PROTECTED
    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();
        const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

        console.log(`🚀 sendMessage() called - ID: ${messageId}`);
        console.log(`📝 Message content: "${message}"`);

        if (!message && this.uploadedFiles.length === 0) {
            console.log('❌ Empty message, returning early');
            return;
        }

        // CRITICAL: Enhanced anti-duplication with message tracking - PROTECTED
        if (this.isSubmitting) {
            console.log(`⛔️ DUPLICATE BLOCKED: Already submitting (ID: ${messageId})`);
            return;
        }

        // Check for trends keywords and auto-load opportunities
        if (this.detectTrendsKeywords(message) && this.trendsEnabled) {
            console.log('📊 Trends keywords detected, loading opportunities...');
            setTimeout(() => {
                this.showTrendsOpportunities();
            }, 1000);
        }

        // Check for image generation commands - Date: 9/28/25
        const imagePrompt = this.detectImageCommands(message);
        if (imagePrompt && this.imageEnabled) {
            console.log(`🎨 Image command detected: "${imagePrompt}"`);
        }

        console.log(`🔒 Setting isSubmitting = true (ID: ${messageId})`);
        this.isSubmitting = true;
        this.lastSubmitTime = Date.now();

        // Disable input while sending
        this.setInputState(false);

        // Add user message to chat with unique ID
        console.log(`👤 Adding user message (ID: ${messageId})`);
        this.addMessage('user', message, {
            files: this.uploadedFiles.slice(),
            clientMessageId: messageId
        });

        // Clear input
        messageInput.value = '';
        this.updateCharCount();
        this.clearUploadedFiles();

        try {
            // Show typing indicator
            this.showTypingIndicator();

            // Enhanced datetime context from working version
            const currentDateTime = new Date();
            const requestData = {
                message: message,
                personality_id: this.currentPersonality,
                thread_id: this.currentThreadId,
                include_knowledge: true,
                client_message_id: messageId, // Track client-side message ID
                context: {
                    current_date: currentDateTime.toISOString().split('T')[0],
                    current_time: currentDateTime.toLocaleTimeString('en-US', { hour12: false }),
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timestamp: currentDateTime.toISOString()
                }
            };

            console.log(`📤 Sending API request (ID: ${messageId}):`, requestData.context);

            // Send request
            const response = await this.apiCall('/ai/chat', 'POST', requestData);

            console.log(`📥 Received API response (ID: ${messageId}):`, {
                messageId: response.message_id,
                threadId: response.thread_id,
                personalityUsed: response.personality_used
            });

            // Update thread ID
            this.currentThreadId = response.thread_id;

            // Hide typing indicator
            this.hideTypingIndicator();

            // Add AI response with response tracking
            console.log(`🤖 Adding AI response (ID: ${messageId} -> ${response.message_id})`);
            const assistantMessage = this.addMessage('assistant', response.response, {
                messageId: response.message_id,
                clientMessageId: messageId,
                personality: response.personality_used,
                responseTime: response.response_time_ms,
                knowledgeSources: response.knowledge_sources || []
            });

            // Voice synthesis for AI response - Date: 9/28/25
            if (this.voiceEnabled && assistantMessage) {
                console.log(`🎤 Starting voice synthesis for response ${response.message_id}`);
                await this.synthesizeVoice(response.response, response.message_id);
            }

            // Image generation if requested - Date: 9/28/25
            if (imagePrompt && this.imageEnabled && assistantMessage) {
                console.log(`🎨 Starting image generation for prompt: "${imagePrompt}"`);
                await this.generateImage(imagePrompt, assistantMessage);
            }

            // Show remember button
            this.showRememberButton(response.message_id);

        } catch (error) {
            console.error(`❌ Chat error (ID: ${messageId}):`, error);
            this.hideTypingIndicator();
            this.addMessage('assistant', 'Sorry, I encountered an error. Please try again.', {
                error: true,
                clientMessageId: messageId
            });
        } finally {
            // CRITICAL: Always re-enable input and reset submission flag - PROTECTED
            console.log(`🔓 Resetting isSubmitting = false (ID: ${messageId})`);
            this.setInputState(true);
            this.isSubmitting = false;
            messageInput.focus();
        }
    }

    handleInputChange() {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        
        this.updateCharCount();
        
        const hasContent = messageInput.value.trim().length > 0 || this.uploadedFiles.length > 0;
        sendButton.disabled = !hasContent || this.isTyping;
        
        this.autoResizeTextarea();
    }

    setInputState(enabled) {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const fileButton = document.getElementById('fileButton');

        messageInput.disabled = !enabled;
        sendButton.disabled = !enabled || this.isSubmitting;
        if (fileButton) fileButton.disabled = !enabled;

        if (enabled) {
            sendButton.classList.remove('loading');
            messageInput.style.opacity = '1';
            sendButton.style.opacity = '1';
        } else {
            sendButton.classList.add('loading');
            messageInput.style.opacity = '0.6';
            sendButton.style.opacity = '0.6';
        }
    }

    // ENHANCED: Message display from working version with feedback buttons + Voice & Image Integration - Date: 9/28/25
    addMessage(role, content, metadata = {}) {
        const messagesContainer = document.getElementById('chatMessages');
        const welcomeMessage = messagesContainer.querySelector('.welcome-message');

        // Remove welcome message on first interaction
        if (welcomeMessage) {
            welcomeMessage.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        messageDiv.dataset.messageId = metadata.messageId || Date.now().toString();

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';

        if (role === 'user') {
            avatar.innerHTML = '👤';
        } else {
            avatar.innerHTML = '<img src="static/syntax-buffering.png" alt="Syntax" style="width: 32px; height: 32px; object-fit: contain; border-radius: 50%;">';
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.innerHTML = this.formatMessageContent(content);

        bubble.appendChild(textDiv);

        // Add file attachments for user messages
        if (role === 'user' && metadata.files && metadata.files.length > 0) {
            const filesDiv = document.createElement('div');
            filesDiv.className = 'message-files';
            metadata.files.forEach(file => {
                const fileSpan = document.createElement('span');
                fileSpan.className = 'message-file';
                fileSpan.innerHTML = `📎 ${file.name}`;
                filesDiv.appendChild(fileSpan);
            });
            bubble.appendChild(filesDiv);
        }

        contentDiv.appendChild(bubble);

        // Add voice controls for assistant messages - Date: 9/28/25
        if (role === 'assistant' && !metadata.error && this.voiceEnabled) {
            const voiceControls = document.createElement('div');
            voiceControls.className = 'voice-controls';
            
            const speakerButton = document.createElement('button');
            speakerButton.className = 'speaker-button';
            speakerButton.title = 'Play Audio';
            speakerButton.innerHTML = '🔊';
            speakerButton.addEventListener('click', () => {
                this.playVoiceMessage(metadata.messageId, speakerButton);
            });
            
            voiceControls.appendChild(speakerButton);
            contentDiv.appendChild(voiceControls);
        }

        // Add message actions for assistant messages with feedback buttons
        if (role === 'assistant' && !metadata.error) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';

            // Create Copy button
            const copyBtn = document.createElement('button');
            copyBtn.className = 'message-action';
            copyBtn.title = 'Copy';
            copyBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
            `;
            copyBtn.addEventListener('click', () => this.copyMessage(metadata.messageId));

            // Create feedback buttons
            const goodBtn = document.createElement('button');
            goodBtn.className = 'message-action feedback-good';
            goodBtn.title = 'Good Answer';
            goodBtn.innerHTML = '👍';
            goodBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'good_answer'));

            const badBtn = document.createElement('button');
            badBtn.className = 'message-action feedback-bad';
            badBtn.title = 'Bad Answer';
            badBtn.innerHTML = '👎';
            badBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'bad_answer'));

            // FIXED: Personality feedback button - Date: 9/28/25
            const personalityBtn = document.createElement('button');
            personalityBtn.className = 'message-action feedback-personality';
            personalityBtn.title = 'Good Personality';
            personalityBtn.innerHTML = '🖕'; // Fixed back to original
            personalityBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'good_personality'));

            actionsDiv.appendChild(copyBtn);
            actionsDiv.appendChild(goodBtn);
            actionsDiv.appendChild(badBtn);
            actionsDiv.appendChild(personalityBtn);

            contentDiv.appendChild(actionsDiv);
        }

        // Add metadata for assistant messages
        if (role === 'assistant' && !metadata.error) {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'message-meta';
            const responseTime = metadata.responseTime ? `${metadata.responseTime}ms` : '';
            metaDiv.innerHTML = `
                <span>Personality: ${metadata.personality}</span>
                ${responseTime ? `<span>Response: ${responseTime}</span>` : ''}
                ${metadata.knowledgeSources?.length ? `<span>Knowledge: ${metadata.knowledgeSources.length} sources</span>` : ''}
            `;
            contentDiv.appendChild(metaDiv);
        }

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Store message content for potential bookmarking
        messageDiv._messageContent = content;
        
        // Return message element for voice/image integration - Date: 9/28/25
        return messageDiv;
    }

    formatMessageContent(content) {
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    autoResizeTextarea() {
        const textarea = document.getElementById('messageInput');
        textarea.style.height = 'auto';
        const newHeight = Math.min(textarea.scrollHeight, 150);
        textarea.style.height = newHeight + 'px';
    }

    updateCharCount() {
        const messageInput = document.getElementById('messageInput');
        const charCount = document.getElementById('charCount');
        
        if (charCount) {
            const count = messageInput.value.length;
            charCount.textContent = `${count}/8000`;
            
            if (count > 7500) {
                charCount.style.color = 'var(--error)';
            } else if (count > 7000) {
                charCount.style.color = 'var(--warning)';
            } else {
                charCount.style.color = 'var(--text-tertiary)';
            }
        }
    }

    showTypingIndicator() {
        this.hideTypingIndicator();
        
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="typing-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;
        
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.appendChild(indicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        this.isTyping = true;
    }

    hideTypingIndicator() {
        const indicator = document.querySelector('.typing-indicator');
        if (indicator) {
            indicator.remove();
        }
        this.isTyping = false;
    }

    // FIXED: Sidebar toggle functionality
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const toggleBtn = document.getElementById('sidebarToggle');
        
        if (sidebar) {
            sidebar.classList.toggle('collapsed');
            
            // Update toggle button icon
            if (sidebar.classList.contains('collapsed')) {
                toggleBtn.innerHTML = `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="3" y1="6" x2="21" y2="6"/>
                        <line x1="3" y1="12" x2="21" y2="12"/>
                        <line x1="3" y1="18" x2="21" y2="18"/>
                    </svg>
                `;
            } else {
                toggleBtn.innerHTML = `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                        <line x1="9" y1="3" x2="9" y2="21"/>
                    </svg>
                `;
            }
        }
    }

    startNewChat() {
        this.currentThreadId = null;
        const messagesContainer = document.getElementById('chatMessages');
        
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <img src="static/syntax-buffering.png" alt="Syntax Prime" style="width: 80px; height: 80px; object-fit: contain;">
                </div>
                <h2>Welcome to Syntax Prime V2</h2>
                <p>Your sarcastic AI assistant with perfect memory and 38% more attitude.</p>
                <div class="welcome-features">
                    <div class="feature-item">
                        <span class="feature-icon">🧠</span>
                        <span>250K Context Memory</span>
                    </div>
                    <div class="feature-item">
                        <span class="feature-icon">📚</span>
                        <span>21K Knowledge Base</span>
                    </div>
                    <div class="feature-item">
                        <span class="feature-icon">🎭</span>
                        <span>4 Unique Personalities</span>
                    </div>
                    <div class="feature-item">
                        <span class="feature-icon">📖</span>
                        <span>Smart Bookmarks</span>
                    </div>
                </div>
            </div>
        `;
        
        console.log('New chat started');
    }

    openSettings() {
        const modal = document.getElementById('settingsModal');
        if (modal) {
            modal.style.display = 'flex';
            
            const defaultPersonality = document.getElementById('defaultPersonality');
            if (defaultPersonality) {
                defaultPersonality.value = this.currentPersonality;
            }
        }
    }

    hideModal(modal) {
        if (modal) {
            modal.style.display = 'none';
        }
    }

    saveSettings() {
        const defaultPersonality = document.getElementById('defaultPersonality');
        const autoSave = document.getElementById('autoSave');
        const showTyping = document.getElementById('showTyping');
        
        if (defaultPersonality) {
            this.currentPersonality = defaultPersonality.value;
            document.getElementById('personalitySelect').value = this.currentPersonality;
        }
        
        const settings = {
            defaultPersonality: this.currentPersonality,
            autoSave: autoSave ? autoSave.checked : true,
            showTyping: showTyping ? showTyping.checked : true
        };
        
        localStorage.setItem('syntaxprime_settings', JSON.stringify(settings));
        this.hideModal(document.getElementById('settingsModal'));
        console.log('Settings saved:', settings);
    }

    logout() {
        // Clean up trends polling
        if (this.trendsPollingInterval) {
            clearInterval(this.trendsPollingInterval);
        }
        
        // Clean up audio - Date: 9/28/25
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio = null;
        }
        
        sessionStorage.removeItem('syntaxprime_auth');
        window.location.href = 'login.html';
    }

    loadPersonalities() {
        const saved = localStorage.getItem('syntaxprime_settings');
        if (saved) {
            try {
                const settings = JSON.parse(saved);
                this.currentPersonality = settings.defaultPersonality || 'syntaxprime';
                document.getElementById('personalitySelect').value = this.currentPersonality;
            } catch (e) {
                console.log('Could not load saved settings');
            }
        }
        console.log('Personalities loaded');
    }

    loadConversations() {
        const conversationsList = document.getElementById('conversationsList');
        if (conversationsList) {
            setTimeout(() => {
                conversationsList.innerHTML = `
                    <div class="conversation-item">
                        <div class="conversation-title">Previous Chat</div>
                        <div class="conversation-preview">How do I fix JavaScript errors?</div>
                        <div class="conversation-time">2 hours ago</div>
                    </div>
                    <div class="conversation-item">
                        <div class="conversation-title">API Debugging</div>
                        <div class="conversation-preview">Help with API integration...</div>
                        <div class="conversation-time">Yesterday</div>
                    </div>
                `;
            }, 1000);
        }
        console.log('Conversations loaded');
    }

    setupDragAndDrop() {
        const dragOverlay = document.getElementById('dragOverlay');
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            document.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            document.addEventListener(eventName, () => {
                if (dragOverlay) dragOverlay.style.display = 'flex';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            document.addEventListener(eventName, () => {
                if (dragOverlay) dragOverlay.style.display = 'none';
            }, false);
        });

        document.addEventListener('drop', this.handleFileSelect.bind(this), false);
        console.log('Drag and drop setup complete');
    }

    handleFileSelect(e) {
        const files = e.dataTransfer ? e.dataTransfer.files : e.target.files;
        
        if (!files || files.length === 0) return;
        
        Array.from(files).forEach(file => {
            if (this.uploadedFiles.length < 5) {
                this.uploadedFiles.push({
                    name: file.name,
                    size: file.size,
                    type: file.type,
                    file: file
                });
            }
        });
        
        this.updateFileDisplay();
        this.handleInputChange();
        
        console.log('Files uploaded:', this.uploadedFiles);
    }

    updateFileDisplay() {
        const fileUploadArea = document.getElementById('fileUploadArea');
        const uploadedFiles = document.getElementById('uploadedFiles');
        
        if (this.uploadedFiles.length > 0) {
            fileUploadArea.style.display = 'block';
            uploadedFiles.innerHTML = this.uploadedFiles.map((file, index) => `
                <div class="uploaded-file">
                    <span class="file-name">${file.name}</span>
                    <button class="remove-file" onclick="window.syntaxPrimeChat.removeFile(${index})">×</button>
                </div>
            `).join('');
        } else {
            fileUploadArea.style.display = 'none';
        }
    }

    removeFile(index) {
        this.uploadedFiles.splice(index, 1);
        this.updateFileDisplay();
        this.handleInputChange();
    }

    clearUploadedFiles() {
        this.uploadedFiles = [];
        this.updateFileDisplay();
    }

    showBookmarkModal() {
        const modal = document.getElementById('bookmarkModal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('bookmarkName').focus();
        }
    }

    saveBookmark() {
        const bookmarkName = document.getElementById('bookmarkName').value.trim();
        if (!bookmarkName) return;
        
        console.log('Saving bookmark:', bookmarkName);
        
        this.hideModal(document.getElementById('bookmarkModal'));
        document.getElementById('bookmarkName').value = '';
    }

    copyMessage(messageId) {
        console.log('Copy message:', messageId);
        // Copy to clipboard functionality
    }

    submitFeedback(messageId, feedbackType) {
        console.log('Feedback submitted:', messageId, feedbackType);
        // Submit feedback to API
    }

    rememberMessage(messageId) {
        console.log('Remember message:', messageId);
        this.showBookmarkModal();
    }

    show
