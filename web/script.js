//=============================================================================
// Syntax Prime V2 - Chat Interface JavaScript
// Session 23: Removed embedded CSS, fixed auto-resize, added random greetings
// Session 26: FIXED - Audio undefined error when messageId not returned by API
// Session 27: Added Project Folders feature - organize conversations into projects
// Original: 9/27/25 - Working sidebar + submit protection + Google Trends
// Updated: Session 23 - CSS moved to style.css, greeting system added
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
        
        // Screen lock recovery system
        this.pendingRequest = null;  // Tracks in-flight request for recovery
        this.wasHiddenDuringRequest = false;
        
        // Project Folders System
        this.projects = [];
        this.selectedProjectId = null;  // null = "All Conversations"
        this.allConversations = [];     // Store all conversations for filtering
        this.contextMenuThreadId = null; // Track which thread context menu is for
        
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
        
        // Voice Synthesis System
        this.voiceEnabled = false;
        this.currentAudio = null;
        this.audioCache = new Map();
        this.voicePersonalities = {
            'syntaxprime': 'adam',
            'syntaxbot': 'josh',
            'nil.exe': 'onyx',
            'ggpt': 'echo'
        };
        
        // Image Generation System
        this.imageEnabled = false;
        this.imageGenerationQueue = [];
        this.currentImageGeneration = null;
        
        // Gesture Video Avatar System
        this.gestureVideoEnabled = true;
        this.gestureVideoElement = null;
        this.defaultGestureVideo = '/static/gestures/default.mp4';
        this.isPlayingGesture = false;
        
        // Random greetings for welcome screen
        this.greetings = [
            { text: "Hey there", subtext: "What can I help you with?" },
            { text: "Good to see you", subtext: "What's on your mind?" },
            { text: "Ready when you are", subtext: "Let's get something done." },
            { text: "What do you need?", subtext: "I'm all ears." },
            { text: "Let's do this", subtext: "What are we working on?" },
            { text: "At your service", subtext: "What can I do for you?" },
            { text: "Hey", subtext: "What's up?" },
            { text: "Alright", subtext: "What do you got for me?" }
        ];
        
        this.init();
    }
    
    // === Initialization ===
    init() {
        this.setupEventListeners();
        this.setupVisibilityListener();  // Screen lock recovery
        this.loadPersonalities();
        this.loadProjects();  // Load projects before conversations
        this.loadConversations();
        this.loadBookmarks();
        this.setupDragAndDrop();
        this.autoResizeTextarea();
        this.initializeTrendsSystem();
        this.initializeVoiceSystem();
        this.initializeImageSystem();
        this.initGestureVideo();
        this.setRandomGreeting();
        this.setupContextMenu();  // Setup context menu for conversations
        
        // Focus message input
        document.getElementById('messageInput').focus();
        
        this.debugDatetimeContext();
    }
    
    // === Screen Lock Recovery System ===
    setupVisibilityListener() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                // Screen is being locked/tab hidden
                if (this.isSubmitting && this.pendingRequest) {
                    console.log('📱 Screen hidden during active request - marking for recovery');
                    this.wasHiddenDuringRequest = true;
                }
            } else {
                // Screen unlocked/tab visible again
                console.log('📱 Screen visible again');
                if (this.wasHiddenDuringRequest && this.pendingRequest) {
                    console.log('🔄 Detected interrupted request - attempting recovery');
                    this.handleInterruptedRequest();
                }
                this.wasHiddenDuringRequest = false;
            }
        });
    }
    
    handleInterruptedRequest() {
        // Check if we still have a pending request that may have been interrupted
        if (!this.pendingRequest) return;
        
        const { message, messageId, startTime } = this.pendingRequest;
        const elapsed = Date.now() - startTime;
        
        // If request has been pending for more than 30 seconds, likely interrupted
        if (elapsed > 30000 && this.isSubmitting) {
            console.log('⚠️ Request likely interrupted by screen lock');
            
            // Hide typing indicator if still showing
            this.hideTypingIndicator();
            
            // Show recovery message with retry option
            this.showInterruptedRequestRecovery(message);
            
            // Reset submission state
            this.isSubmitting = false;
            this.setInputState(true);
            this.pendingRequest = null;
        }
    }
    
    showInterruptedRequestRecovery(originalMessage) {
        const messagesContainer = document.getElementById('chatMessages');
        
        // Create recovery message
        const recoveryDiv = document.createElement('div');
        recoveryDiv.className = 'message system recovery-message';
        recoveryDiv.innerHTML = `
            <div class="message-content">
                <div class="message-bubble" style="background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.3);">
                    <div class="message-text">
                        <p style="margin: 0 0 8px 0;">⚠️ Connection interrupted (screen locked during request)</p>
                        <button class="retry-button" style="
                            background: var(--accent);
                            color: white;
                            border: none;
                            padding: 8px 16px;
                            border-radius: 6px;
                            cursor: pointer;
                            font-size: 14px;
                        ">🔄 Retry Message</button>
                        <button class="dismiss-button" style="
                            background: transparent;
                            color: var(--text-secondary);
                            border: 1px solid var(--border);
                            padding: 8px 16px;
                            border-radius: 6px;
                            cursor: pointer;
                            font-size: 14px;
                            margin-left: 8px;
                        ">Dismiss</button>
                    </div>
                </div>
            </div>
        `;
        
        // Add retry handler
        const retryBtn = recoveryDiv.querySelector('.retry-button');
        retryBtn.addEventListener('click', () => {
            recoveryDiv.remove();
            // Re-populate input and trigger send
            document.getElementById('messageInput').value = originalMessage;
            this.sendMessage();
        });
        
        // Add dismiss handler
        const dismissBtn = recoveryDiv.querySelector('.dismiss-button');
        dismissBtn.addEventListener('click', () => {
            recoveryDiv.remove();
        });
        
        messagesContainer.appendChild(recoveryDiv);
        recoveryDiv.scrollIntoView({ behavior: 'smooth' });
    }
    
    // === Gesture Video Avatar System ===
    initGestureVideo() {
        // Create gesture video container (hidden initially)
        const chatContainer = document.querySelector('.chat-container');
        if (!chatContainer) {
            console.warn('🎭 Chat container not found - gesture video init skipped');
            return;
        }
        
        const gestureContainer = document.createElement('div');
        gestureContainer.className = 'gesture-video-container hidden';
        gestureContainer.id = 'gestureVideoContainer';
        gestureContainer.innerHTML = `
            <div class="gesture-video-wrapper" id="gestureVideoWrapper">
                <video class="gesture-video" id="gestureVideo" muted playsinline>
                    <source src="${this.defaultGestureVideo}" type="video/mp4">
                </video>
            </div>
        `;
        
        // Insert at the beginning of chat container (before chat-messages)
        const chatMessages = chatContainer.querySelector('.chat-messages');
        if (chatMessages) {
            chatContainer.insertBefore(gestureContainer, chatMessages);
        } else {
            chatContainer.insertBefore(gestureContainer, chatContainer.firstChild);
        }
        
        this.gestureVideoElement = document.getElementById('gestureVideo');
        
        // When gesture video ends, return to default loop
        if (this.gestureVideoElement) {
            this.gestureVideoElement.addEventListener('ended', () => {
                if (this.isPlayingGesture) {
                    this.playDefaultGesture();
                }
            });
            
            // Handle video errors gracefully
            this.gestureVideoElement.addEventListener('error', (e) => {
                console.warn('🎭 Gesture video error:', e);
                // Try to recover by playing default
                setTimeout(() => this.playDefaultGesture(), 1000);
            });
        }
        
        console.log('🎭 Gesture video system initialized');
    }
    
    showGestureVideo() {
        if (!this.gestureVideoEnabled) return;
        
        const container = document.getElementById('gestureVideoContainer');
        const chatContainer = document.querySelector('.chat-container');
        
        if (container && !container.classList.contains('hidden')) {
            // Already visible
            return;
        }
        
        if (container) {
            container.classList.remove('hidden');
            chatContainer?.classList.add('has-gesture-video');
            
            // Start default loop if not already playing
            if (this.gestureVideoElement) {
                this.playDefaultGesture();
            }
            
            console.log('🎭 Gesture video shown');
        }
    }
    
    hideGestureVideo() {
        const container = document.getElementById('gestureVideoContainer');
        const chatContainer = document.querySelector('.chat-container');
        
        if (container) {
            container.classList.add('hidden');
            chatContainer?.classList.remove('has-gesture-video');
            
            if (this.gestureVideoElement) {
                this.gestureVideoElement.pause();
            }
            this.isPlayingGesture = false;
            
            console.log('🎭 Gesture video hidden');
        }
    }
    
    playDefaultGesture() {
        if (!this.gestureVideoElement) return;
        
        const wrapper = document.getElementById('gestureVideoWrapper');
        wrapper?.classList.remove('playing-gesture');
        
        this.gestureVideoElement.src = this.defaultGestureVideo;
        this.gestureVideoElement.loop = true;
        this.isPlayingGesture = false;
        
        this.gestureVideoElement.play().catch(e => {
            console.log('🎭 Auto-play blocked (expected on first load):', e.message);
        });
    }
    
    playGesture(videoUrl) {
        if (!this.gestureVideoElement || !videoUrl) return;
        
        const wrapper = document.getElementById('gestureVideoWrapper');
        wrapper?.classList.add('playing-gesture');
        
        console.log(`🎭 Playing gesture: ${videoUrl}`);
        
        this.gestureVideoElement.src = videoUrl;
        this.gestureVideoElement.loop = false;
        this.isPlayingGesture = true;
        
        this.gestureVideoElement.play().catch(e => {
            console.warn('🎭 Gesture play failed:', e.message);
            // Fall back to default on error
            this.playDefaultGesture();
        });
    }
    
    handleGestureFromResponse(response) {
        if (!this.gestureVideoEnabled) return;
        
        // Show video container when chat is active
        this.showGestureVideo();
        
        // If response has gesture, play it
        if (response.gesture && response.gesture.video_url) {
            this.playGesture(response.gesture.video_url);
        }
        // If no gesture detected, just keep playing default (already looping)
    }
    
    // === Random Greeting System ===
    getTimeBasedGreeting() {
        const hour = new Date().getHours();
        if (hour < 12) return "Good morning";
        if (hour < 18) return "Good afternoon";
        return "Good evening";
    }
    
    getRandomGreeting() {
        // 30% chance to use time-based greeting
        if (Math.random() < 0.3) {
            return {
                text: this.getTimeBasedGreeting(),
                subtext: "What can I help you with?"
            };
        }
        // 70% chance to use random greeting
        return this.greetings[Math.floor(Math.random() * this.greetings.length)];
    }
    
    setRandomGreeting() {
        const greetingText = document.getElementById('greetingText');
        const greetingSubtext = document.getElementById('greetingSubtext');
        
        if (greetingText && greetingSubtext) {
            const greeting = this.getRandomGreeting();
            greetingText.textContent = greeting.text;
            greetingSubtext.textContent = greeting.subtext;
        }
    }
    
    debugDatetimeContext() {
        const now = new Date();
        console.log('🕘 Frontend Datetime Context:');
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
        
        // Project buttons
        const addProjectBtn = document.getElementById('addProjectBtn');
        if (addProjectBtn && !addProjectBtn._syntaxListenersAttached) {
            addProjectBtn.addEventListener('click', this.showNewProjectModal.bind(this));
            addProjectBtn._syntaxListenersAttached = true;
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
        
        // Drive modal handlers
        const driveModal = document.getElementById('driveModal');
        const closeDriveModal = document.getElementById('closeDriveModal');
        const cancelDrive = document.getElementById('cancelDrive');
        const saveDrive = document.getElementById('saveDrive');
        
        if (closeDriveModal) closeDriveModal.addEventListener('click', () => this.hideModal(driveModal));
        if (cancelDrive) cancelDrive.addEventListener('click', () => this.hideModal(driveModal));
        if (saveDrive) saveDrive.addEventListener('click', this.saveDriveDoc.bind(this));
        
        // Settings modal
        const settingsModal = document.getElementById('settingsModal');
        const closeSettingsModal = document.getElementById('closeSettingsModal');
        const saveSettingsBtn = document.getElementById('saveSettings');
        
        if (closeSettingsModal) closeSettingsModal.addEventListener('click', () => this.hideModal(settingsModal));
        if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', this.saveSettings.bind(this));
        
        // Project modal handlers
        this.setupProjectModalHandlers();
        
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
    
    // === Project Modal Handlers ===
    setupProjectModalHandlers() {
        // New Project Modal
        const newProjectModal = document.getElementById('newProjectModal');
        const closeNewProjectModal = document.getElementById('closeNewProjectModal');
        const cancelNewProject = document.getElementById('cancelNewProject');
        const saveNewProject = document.getElementById('saveNewProject');
        
        if (closeNewProjectModal) closeNewProjectModal.addEventListener('click', () => this.hideModal(newProjectModal));
        if (cancelNewProject) cancelNewProject.addEventListener('click', () => this.hideModal(newProjectModal));
        if (saveNewProject) saveNewProject.addEventListener('click', this.createProject.bind(this));
        
        // Edit Project Modal
        const editProjectModal = document.getElementById('editProjectModal');
        const closeEditProjectModal = document.getElementById('closeEditProjectModal');
        const cancelEditProject = document.getElementById('cancelEditProject');
        const saveEditProject = document.getElementById('saveEditProject');
        const deleteProject = document.getElementById('deleteProject');
        
        if (closeEditProjectModal) closeEditProjectModal.addEventListener('click', () => this.hideModal(editProjectModal));
        if (cancelEditProject) cancelEditProject.addEventListener('click', () => this.hideModal(editProjectModal));
        if (saveEditProject) saveEditProject.addEventListener('click', this.updateProject.bind(this));
        if (deleteProject) deleteProject.addEventListener('click', this.deleteProject.bind(this));
        
        // Move to Project Modal
        const moveToProjectModal = document.getElementById('moveToProjectModal');
        const closeMoveToProjectModal = document.getElementById('closeMoveToProjectModal');
        const cancelMoveToProject = document.getElementById('cancelMoveToProject');
        const confirmMoveToProject = document.getElementById('confirmMoveToProject');
        
        if (closeMoveToProjectModal) closeMoveToProjectModal.addEventListener('click', () => this.hideModal(moveToProjectModal));
        if (cancelMoveToProject) cancelMoveToProject.addEventListener('click', () => this.hideModal(moveToProjectModal));
        if (confirmMoveToProject) confirmMoveToProject.addEventListener('click', this.moveThreadToProject.bind(this));
        
        // Setup color pickers
        this.setupColorPicker('newProjectColorPicker', 'newProjectPreviewColor');
        this.setupColorPicker('editProjectColorPicker', 'editProjectPreviewColor');
        
        // Setup icon pickers
        this.setupIconPicker('newProjectIconPicker', 'newProjectPreviewIcon');
        this.setupIconPicker('editProjectIconPicker', 'editProjectPreviewIcon');
        
        // Setup live preview updates for new project
        const newProjectName = document.getElementById('newProjectName');
        const newProjectDisplayName = document.getElementById('newProjectDisplayName');
        if (newProjectName) {
            newProjectName.addEventListener('input', () => this.updateProjectPreview('new'));
        }
        if (newProjectDisplayName) {
            newProjectDisplayName.addEventListener('input', () => this.updateProjectPreview('new'));
        }
        
        // Setup live preview updates for edit project
        const editProjectName = document.getElementById('editProjectName');
        const editProjectDisplayName = document.getElementById('editProjectDisplayName');
        if (editProjectName) {
            editProjectName.addEventListener('input', () => this.updateProjectPreview('edit'));
        }
        if (editProjectDisplayName) {
            editProjectDisplayName.addEventListener('input', () => this.updateProjectPreview('edit'));
        }
        
        // Close modals on outside click
        [newProjectModal, editProjectModal, moveToProjectModal].forEach(modal => {
            if (modal) {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        this.hideModal(modal);
                    }
                });
            }
        });
    }
    
    setupColorPicker(pickerId, previewId) {
        const picker = document.getElementById(pickerId);
        if (!picker) return;
        
        const swatches = picker.querySelectorAll('.color-swatch');
        swatches.forEach(swatch => {
            swatch.addEventListener('click', () => {
                // Remove selected from all
                swatches.forEach(s => s.classList.remove('selected'));
                // Add selected to clicked
                swatch.classList.add('selected');
                // Update preview
                const preview = document.getElementById(previewId);
                if (preview) {
                    preview.style.background = swatch.dataset.color;
                }
            });
        });
    }
    
    setupIconPicker(pickerId, previewId) {
        const picker = document.getElementById(pickerId);
        if (!picker) return;
        
        const options = picker.querySelectorAll('.icon-option');
        options.forEach(option => {
            option.addEventListener('click', (e) => {
                e.preventDefault();
                // Remove selected from all
                options.forEach(o => o.classList.remove('selected'));
                // Add selected to clicked
                option.classList.add('selected');
                // Update preview
                const preview = document.getElementById(previewId);
                if (preview) {
                    preview.textContent = option.dataset.icon;
                }
            });
        });
    }
    
    updateProjectPreview(type) {
        const prefix = type === 'new' ? 'newProject' : 'editProject';
        const nameInput = document.getElementById(`${prefix}Name`);
        const displayNameInput = document.getElementById(`${prefix}DisplayName`);
        const previewName = document.getElementById(`${prefix}PreviewName`);
        const previewDisplayName = document.getElementById(`${prefix}PreviewDisplayName`);
        
        if (previewName && nameInput) {
            previewName.textContent = nameInput.value || 'Project Name';
        }
        if (previewDisplayName && displayNameInput) {
            previewDisplayName.textContent = displayNameInput.value || 'Display Name';
        }
    }
    
    // === Voice Synthesis Integration ===
    async initializeVoiceSystem() {
        try {
            console.log('🎤 Initializing Voice Synthesis system...');
            
            this.voiceEnabled = true; // Force enable for testing
            
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
            
            // FIXED: Validate messageId before making API call
            if (!messageId || messageId === 'undefined' || messageId === 'null') {
                console.warn('⚠️ Invalid messageId for voice playback:', messageId);
                this.showToast('❌ Cannot play audio - missing message ID', 'error');
                return;
            }
            
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
                
                // Check local cache first
                let audioUrl = this.audioCache.get(messageId);
                
                if (!audioUrl) {
                    // FIXED: Call /synthesize first - it handles caching internally
                    // Get message text from the DOM
                    const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
                    const messageText = messageElement ? messageElement.getAttribute('data-raw-markdown') : null;
                    
                    if (!messageText) {
                        throw new Error('Could not find message text for audio synthesis');
                    }
                    
                    console.log(`🎤 Requesting audio synthesis for message ${messageId}`);
                    
                    // Call synthesize endpoint (returns cached audio if exists, generates if not)
                    const response = await this.apiCall('/api/voice/synthesize', 'POST', {
                        text: messageText,
                        message_id: messageId,
                        personality_id: this.currentPersonality || 'syntaxprime'
                    });
                    
                    if (response && response.success && response.audio_url) {
                        audioUrl = response.audio_url;
                        this.audioCache.set(messageId, audioUrl);
                        console.log(`✅ Audio ready for message ${messageId} (cached: ${response.cached})`);
                    } else {
                        throw new Error(response?.error || 'Audio synthesis failed');
                    }
                }
                
                // Create and play audio - audioUrl is the direct endpoint path
                const fullAudioUrl = audioUrl.startsWith('http') ? audioUrl : `${this.apiBase}${audioUrl}`;
                const audio = new Audio(fullAudioUrl);
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
                
                audio.onerror = (e) => {
                    console.error('Audio playback failed:', e);
                    this.clearPlayingStates();
                    this.hideWaveformAnimation(speakerButton);
                    speakerButton.innerHTML = '🔊';
                    speakerButton.classList.remove('loading', 'playing');
                    this.showToast('❌ Audio playback failed', 'error');
                };
                
                await audio.play();
                console.log(`🔊 Playing voice for message ${messageId}`);
                
            } catch (error) {
                console.error('Voice playback failed:', error);
                speakerButton.classList.remove('loading', 'playing');
                speakerButton.innerHTML = '🔊';
                this.showToast(`❌ ${error.message || 'Voice playback failed'}`, 'error');
            }
        }
    
    clearPlayingStates() {
        const playingButtons = document.querySelectorAll('.speaker-button.playing');
        playingButtons.forEach(btn => {
            btn.classList.remove('playing');
            this.hideWaveformAnimation(btn);
        });
    }
    
    showWaveformAnimation(speakerButton) {
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
    
    // === Image Generation Integration ===
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
            
            console.log('💾 Image downloaded');
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
        console.log(`🔍 Message content: "${message}"`);
        
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
        
        // Check for image generation commands
        const imagePrompt = this.detectImageCommands(message);
        if (imagePrompt && this.imageEnabled) {
            console.log(`🎨 Image command detected: "${imagePrompt}"`);
        }
        
        console.log(`🔒 Setting isSubmitting = true (ID: ${messageId})`);
        this.isSubmitting = true;
        this.lastSubmitTime = Date.now();
        
        // Track pending request for screen lock recovery
        this.pendingRequest = {
            message: message,
            messageId: messageId,
            startTime: Date.now()
        };
        
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
        this.autoResizeTextarea();
        
        try {
            // Show typing indicator
            this.showTypingIndicator();
            
            // FIXED: Create FormData instead of JSON object
            const formData = new FormData();
            formData.append('message', message);
            formData.append('personality_id', this.currentPersonality);
            
            if (this.currentThreadId) {
                formData.append('thread_id', this.currentThreadId);
            }
            
            // Add project_id if a project is selected
            if (this.selectedProjectId) {
                formData.append('project_id', this.selectedProjectId);
            }
            
            formData.append('include_knowledge', 'true');
            
            // Add uploaded files if any - FIXED: Must verify File objects exist
            if (this.uploadedFiles && this.uploadedFiles.length > 0) {
                console.log('📎 Adding files to FormData:', this.uploadedFiles.length);
                for (const fileObj of this.uploadedFiles) {
                    // Verify we have a valid File object
                    if (fileObj.file && fileObj.file instanceof File) {
                        console.log('  ✅ Adding file:', fileObj.file.name, 'Type:', fileObj.file.type, 'Size:', fileObj.file.size);
                        formData.append('files', fileObj.file, fileObj.file.name);
                    } else {
                        console.error('  ❌ Invalid file object:', fileObj);
                    }
                }
                
                // NOW clear the uploaded files after adding to FormData
                this.clearUploadedFiles();
            } else {
                console.log('📎 No files to upload');
            }
            
            console.log(`📤 Sending API request (ID: ${messageId}) with FormData`);
            
            // Send request - apiCall will handle FormData correctly
            const response = await this.apiCall('/ai/chat', 'POST', formData);
            
            console.log(`📥 Received API response (ID: ${messageId}):`, {
                messageId: response.message_id,
                threadId: response.thread_id,
                personalityUsed: response.personality_used
            });
            
            // Update thread ID
            this.currentThreadId = response.thread_id;
            
            // Clear pending request - success!
            this.pendingRequest = null;
            
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
            
            // Handle gesture video animation
            this.handleGestureFromResponse(response);
            
            // Image generation if requested
            if (imagePrompt && this.imageEnabled && assistantMessage) {
                console.log(`🎨 Starting image generation for prompt: "${imagePrompt}"`);
                await this.generateImage(imagePrompt, assistantMessage);
            }
            
            // Show remember button
            this.showRememberButton(response.message_id);
            
            // Reload conversations to update sidebar
            await this.loadConversations();
            
        } catch (error) {
            console.error(`❌ Chat error (ID: ${messageId}):`, error);
            this.hideTypingIndicator();
            
            // Check if this might be a screen lock interruption
            const isAbortError = error.name === 'AbortError' ||
                                 error.message.includes('aborted') ||
                                 error.message.includes('Failed to fetch');
            
            if (isAbortError && this.wasHiddenDuringRequest) {
                // Don't show generic error - let visibility handler deal with it
                console.log('🔄 Request aborted during screen lock - recovery will handle');
            } else {
                // Regular error - show message
                this.addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
                this.pendingRequest = null;  // Clear on regular error
            }
        } finally {
            // Always reset submission state (unless waiting for recovery)
            if (!this.wasHiddenDuringRequest || !this.pendingRequest) {
                console.log(`🔓 Resetting isSubmitting = false (ID: ${messageId})`);
                this.isSubmitting = false;
                this.setInputState(true);
            } else {
                console.log(`⏳ Keeping submission state for potential recovery (ID: ${messageId})`);
            }
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
    
    // ENHANCED: Message display with feedback buttons + Voice & Image Integration
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
        messageDiv.setAttribute('data-raw-markdown', content);
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
        
        // Add voice controls for assistant messages
        if (role === 'assistant' && !metadata.error && this.voiceEnabled) {
            // Only add voice if we have a valid messageId
            const voiceMessageId = metadata.messageId || messageDiv.dataset.messageId;
            if (voiceMessageId && voiceMessageId !== 'undefined') {
                const voiceControls = document.createElement('div');
                voiceControls.className = 'voice-controls';
                
                const speakerButton = document.createElement('button');
                speakerButton.className = 'speaker-button';
                speakerButton.title = 'Play Audio';
                speakerButton.innerHTML = '🔊';
                speakerButton.addEventListener('click', () => {
                    this.playVoiceMessage(voiceMessageId, speakerButton);
                });
                
                voiceControls.appendChild(speakerButton);
                contentDiv.appendChild(voiceControls);
            }
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
            goodBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'good'));
            
            const badBtn = document.createElement('button');
            badBtn.className = 'message-action feedback-bad';
            badBtn.title = 'Bad Answer';
            badBtn.innerHTML = '👎';
            badBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'bad'));
            
            // Personality feedback button
            const personalityBtn = document.createElement('button');
            personalityBtn.className = 'message-action feedback-personality';
            personalityBtn.title = 'Good Personality';
            personalityBtn.innerHTML = '🖕';
            personalityBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'personality'));
            
            // Bookmark button
            const bookmarkBtn = document.createElement('button');
            bookmarkBtn.className = 'message-action bookmark-btn';
            bookmarkBtn.title = 'Bookmark This';
            bookmarkBtn.innerHTML = '📌';
            bookmarkBtn.addEventListener('click', () => this.rememberMessage(metadata.messageId));
            
            // Drive button
            const driveBtn = document.createElement('button');
            driveBtn.className = 'message-action drive-btn';
            driveBtn.title = 'Copy to Google Drive';
            driveBtn.innerHTML = '💾';
            driveBtn.addEventListener('click', () => this.copyToDrive(metadata.messageId));
            
            actionsDiv.appendChild(copyBtn);
            actionsDiv.appendChild(goodBtn);
            actionsDiv.appendChild(badBtn);
            actionsDiv.appendChild(personalityBtn);
            actionsDiv.appendChild(bookmarkBtn);
            actionsDiv.appendChild(driveBtn);
            
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
        
        // Return message element for voice/image integration
        return messageDiv;
    }
    
    formatMessageContent(content) {
        // First, check if content contains image data
        const imageDataRegex = /<IMAGE_DATA>(.*?)<\/IMAGE_DATA>/gs;
        const imageMatch = content.match(imageDataRegex);
        
        if (imageMatch) {
            // Extract the base64 data
            const base64Data = imageMatch[0].replace(/<IMAGE_DATA>/g, '').replace(/<\/IMAGE_DATA>/g, '').trim();
            
            // Remove the IMAGE_DATA tags from content
            content = content.replace(imageDataRegex, '');
            
            // Format the rest of the content
            const formattedContent = content
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/`(.*?)`/g, '<code>$1</code>')
                .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="download-link">$1</a>')
                .replace(/\n/g, '<br>');
            
            // Add the image at the end with proper styling
            return `${formattedContent}
                <div class="generated-image-container" style="margin-top: 16px; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <img src="data:image/png;base64,${base64Data}" 
                         alt="Generated Image" 
                         style="width: 100%; height: auto; display: block; max-width: 512px;" 
                         loading="lazy" />
                </div>`;
        }
        
        // No image data, just format normally
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="download-link">$1</a>')
            .replace(/\n/g, '<br>');
    }
    
    // FIXED: Auto-resize textarea - now properly resizes on input
    autoResizeTextarea() {
        const textarea = document.getElementById('messageInput');
        if (!textarea) return;
        
        // Reset height to auto to get accurate scrollHeight
        textarea.style.height = 'auto';
        
        // Calculate new height with min (48px) and max (200px) constraints
        const minHeight = 48;
        const maxHeight = 200;
        const newHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight));
        
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
            sidebar.classList.toggle('open');
            
            // Update toggle button icon
            if (sidebar.classList.contains('open')) {
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
    
    // UPDATED: Start new chat with simplified greeting and project support
    startNewChat() {
        this.currentThreadId = null;
        
        // Hide gesture video when starting fresh
        this.hideGestureVideo();
        
        const messagesContainer = document.getElementById('chatMessages');
        
        // Get a fresh random greeting
        const greeting = this.getRandomGreeting();
        
        // Build project indicator HTML if a project is selected
        let projectIndicatorHtml = '';
        if (this.selectedProjectId) {
            const project = this.projects.find(p => p.id === this.selectedProjectId);
            if (project) {
                projectIndicatorHtml = `
                    <div class="welcome-project-indicator">
                        <span class="project-icon">${project.icon || '📁'}</span>
                        <span>New chat in ${project.display_name || project.name}</span>
                    </div>
                `;
            }
        }
        
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <img src="static/syntax-buffering.png" alt="Syntax Prime" style="width: 64px; height: 64px; object-fit: contain;">
                </div>
                <h2 id="greetingText">${greeting.text}</h2>
                <p id="greetingSubtext">${greeting.subtext}</p>
                ${projectIndicatorHtml}
            </div>
        `;
        
        console.log('New chat started' + (this.selectedProjectId ? ` in project ${this.selectedProjectId}` : ''));
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
            modal.classList.remove('active');
            setTimeout(() => {
                modal.style.display = 'none';
            }, 300);
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
        
        // Clean up audio
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
    
    // === Project Folders System ===
    async loadProjects() {
        try {
            console.log('📁 Loading projects...');
            const response = await this.apiCall('/ai/projects', 'GET');
            
            if (response && response.projects) {
                this.projects = response.projects;
                this.renderProjects();
                console.log(`📁 Loaded ${this.projects.length} projects`);
            }
        } catch (error) {
            console.error('Failed to load projects:', error);
            // Show empty state instead of error
            this.projects = [];
            this.renderProjects();
        }
    }
    
    renderProjects() {
        const projectsList = document.getElementById('projectsList');
        const projectCount = document.getElementById('projectCount');
        
        if (!projectsList) return;
        
        // Update count
        if (projectCount) {
            projectCount.textContent = this.projects.length;
        }
        
        // Build HTML
        let html = '';
        
        // "All Conversations" option
        html += `
            <div class="project-item-all ${this.selectedProjectId === null ? 'active' : ''}" 
                 data-project-id="all"
                 onclick="window.syntaxPrimeChat.selectProject(null)">
                <div class="project-icon">💬</div>
                <div class="project-name">All Conversations</div>
            </div>
        `;
        
        if (this.projects.length === 0) {
            html += `
                <div class="no-projects">
                    <p>No projects yet</p>
                    <small>Click + to create your first project</small>
                </div>
            `;
        } else {
            // Render each project
            this.projects.forEach(project => {
                const isActive = this.selectedProjectId === project.id;
                html += `
                    <div class="project-item ${isActive ? 'active' : ''}" 
                         data-project-id="${project.id}"
                         onclick="window.syntaxPrimeChat.selectProject(${project.id})">
                        <div class="project-color-indicator" style="background: ${project.color || '#7b61ff'};"></div>
                        <div class="project-icon">${project.icon || '📁'}</div>
                        <div class="project-info">
                            <div class="project-name">${project.display_name || project.name}</div>
                            <div class="project-thread-count">${project.thread_count || 0} chats</div>
                        </div>
                        <button class="project-item-menu-btn" onclick="event.stopPropagation(); window.syntaxPrimeChat.showEditProjectModal(${project.id});" title="Edit Project">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="1"/>
                                <circle cx="12" cy="5" r="1"/>
                                <circle cx="12" cy="19" r="1"/>
                            </svg>
                        </button>
                    </div>
                `;
            });
        }
        
        projectsList.innerHTML = html;
    }
    
    selectProject(projectId) {
        console.log(`📁 Selected project: ${projectId}`);
        this.selectedProjectId = projectId;
        
        // Update project list UI
        this.renderProjects();
        
        // Filter conversations
        this.filterConversationsByProject(projectId);
        
        // Update welcome screen project indicator
        this.updateWelcomeProjectIndicator();
    }
    
    updateWelcomeProjectIndicator() {
        const indicator = document.getElementById('welcomeProjectIndicator');
        const iconEl = document.getElementById('welcomeProjectIcon');
        const nameEl = document.getElementById('welcomeProjectName');
        
        if (!indicator) return;
        
        if (this.selectedProjectId) {
            const project = this.projects.find(p => p.id === this.selectedProjectId);
            if (project) {
                indicator.style.display = 'flex';
                if (iconEl) iconEl.textContent = project.icon || '📁';
                if (nameEl) nameEl.textContent = `New chat in ${project.display_name || project.name}`;
            }
        } else {
            indicator.style.display = 'none';
        }
    }
    
    filterConversationsByProject(projectId) {
        if (projectId === null) {
            // Show all conversations
            this.renderConversations(this.allConversations);
        } else {
            // Filter to only show conversations in this project
            const filtered = this.allConversations.filter(conv => conv.primary_project_id === projectId);
            this.renderConversations(filtered);
        }
    }
    
    showNewProjectModal() {
        const modal = document.getElementById('newProjectModal');
        if (!modal) return;
        
        // Reset form
        document.getElementById('newProjectName').value = '';
        document.getElementById('newProjectDisplayName').value = '';
        document.getElementById('newProjectDescription').value = '';
        document.getElementById('newProjectInstructions').value = '';
        
        // Reset color picker - select first
        const colorSwatches = document.querySelectorAll('#newProjectColorPicker .color-swatch');
        colorSwatches.forEach((s, i) => s.classList.toggle('selected', i === 0));
        document.getElementById('newProjectPreviewColor').style.background = '#EF4444';
        
        // Reset icon picker - select first
        const iconOptions = document.querySelectorAll('#newProjectIconPicker .icon-option');
        iconOptions.forEach((o, i) => o.classList.toggle('selected', i === 0));
        document.getElementById('newProjectPreviewIcon').textContent = '📁';
        
        // Reset preview
        document.getElementById('newProjectPreviewName').textContent = 'Project Name';
        document.getElementById('newProjectPreviewDisplayName').textContent = 'Display Name';
        
        // Show modal
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('active'), 10);
        
        // Focus name input
        document.getElementById('newProjectName').focus();
    }
    
    async createProject() {
        const name = document.getElementById('newProjectName').value.trim();
        const displayName = document.getElementById('newProjectDisplayName').value.trim();
        const description = document.getElementById('newProjectDescription').value.trim();
        const instructions = document.getElementById('newProjectInstructions').value.trim();
        
        // Get selected color
        const selectedColor = document.querySelector('#newProjectColorPicker .color-swatch.selected');
        const color = selectedColor ? selectedColor.dataset.color : '#7b61ff';
        
        // Get selected icon
        const selectedIcon = document.querySelector('#newProjectIconPicker .icon-option.selected');
        const icon = selectedIcon ? selectedIcon.dataset.icon : '📁';
        
        // Validate
        if (!name) {
            this.showToast('❌ Please enter a project name', 'error');
            return;
        }
        
        // Validate name format (no spaces, alphanumeric + dash/underscore)
        if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
            this.showToast('❌ Project name can only contain letters, numbers, dashes, and underscores', 'error');
            return;
        }
        
        try {
            const response = await this.apiCall('/ai/projects', 'POST', {
                name: name,
                display_name: displayName || name,
                description: description || null,
                instructions: instructions || null,
                color: color,
                icon: icon
            });
            
            if (response && response.project) {
                this.showToast('✅ Project created!', 'success');
                this.hideModal(document.getElementById('newProjectModal'));
                
                // Reload projects
                await this.loadProjects();
                
                // Select the new project
                this.selectProject(response.project.id);
            }
        } catch (error) {
            console.error('Failed to create project:', error);
            this.showToast('❌ Failed to create project', 'error');
        }
    }
    
    showEditProjectModal(projectId) {
        const project = this.projects.find(p => p.id === projectId);
        if (!project) return;
        
        const modal = document.getElementById('editProjectModal');
        if (!modal) return;
        
        // Fill form with project data
        document.getElementById('editProjectId').value = project.id;
        document.getElementById('editProjectName').value = project.name;
        document.getElementById('editProjectDisplayName').value = project.display_name || '';
        document.getElementById('editProjectDescription').value = project.description || '';
        document.getElementById('editProjectInstructions').value = project.instructions || '';
        
        // Set color picker
        const colorSwatches = document.querySelectorAll('#editProjectColorPicker .color-swatch');
        colorSwatches.forEach(s => {
            s.classList.toggle('selected', s.dataset.color === project.color);
        });
        document.getElementById('editProjectPreviewColor').style.background = project.color || '#7b61ff';
        
        // Set icon picker
        const iconOptions = document.querySelectorAll('#editProjectIconPicker .icon-option');
        iconOptions.forEach(o => {
            o.classList.toggle('selected', o.dataset.icon === project.icon);
        });
        document.getElementById('editProjectPreviewIcon').textContent = project.icon || '📁';
        
        // Update preview
        document.getElementById('editProjectPreviewName').textContent = project.name;
        document.getElementById('editProjectPreviewDisplayName').textContent = project.display_name || project.name;
        
        // Show modal
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('active'), 10);
    }
    
    async updateProject() {
        const projectId = document.getElementById('editProjectId').value;
        const name = document.getElementById('editProjectName').value.trim();
        const displayName = document.getElementById('editProjectDisplayName').value.trim();
        const description = document.getElementById('editProjectDescription').value.trim();
        const instructions = document.getElementById('editProjectInstructions').value.trim();
        
        // Get selected color
        const selectedColor = document.querySelector('#editProjectColorPicker .color-swatch.selected');
        const color = selectedColor ? selectedColor.dataset.color : '#7b61ff';
        
        // Get selected icon
        const selectedIcon = document.querySelector('#editProjectIconPicker .icon-option.selected');
        const icon = selectedIcon ? selectedIcon.dataset.icon : '📁';
        
        // Validate
        if (!name) {
            this.showToast('❌ Please enter a project name', 'error');
            return;
        }
        
        if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
            this.showToast('❌ Project name can only contain letters, numbers, dashes, and underscores', 'error');
            return;
        }
        
        try {
            const response = await this.apiCall(`/ai/projects/${projectId}`, 'PUT', {
                name: name,
                display_name: displayName || name,
                description: description || null,
                instructions: instructions || null,
                color: color,
                icon: icon
            });
            
            if (response && response.project) {
                this.showToast('✅ Project updated!', 'success');
                this.hideModal(document.getElementById('editProjectModal'));
                
                // Reload projects
                await this.loadProjects();
            }
        } catch (error) {
            console.error('Failed to update project:', error);
            this.showToast('❌ Failed to update project', 'error');
        }
    }
    
    async deleteProject() {
        const projectId = document.getElementById('editProjectId').value;
        const project = this.projects.find(p => p.id == projectId);
        
        if (!confirm(`Are you sure you want to delete "${project?.display_name || project?.name}"?\n\nConversations will NOT be deleted, they will just be unassigned from this project.`)) {
            return;
        }
        
        try {
            await this.apiCall(`/ai/projects/${projectId}`, 'DELETE');
            
            this.showToast('✅ Project deleted', 'success');
            this.hideModal(document.getElementById('editProjectModal'));
            
            // If this was the selected project, deselect it
            if (this.selectedProjectId == projectId) {
                this.selectedProjectId = null;
            }
            
            // Reload projects and conversations
            await this.loadProjects();
            await this.loadConversations();
        } catch (error) {
            console.error('Failed to delete project:', error);
            this.showToast('❌ Failed to delete project', 'error');
        }
    }
    
    // === Context Menu for Conversations ===
    setupContextMenu() {
        const contextMenu = document.getElementById('conversationContextMenu');
        if (!contextMenu) return;
        
        // Close context menu on click outside
        document.addEventListener('click', (e) => {
            if (!contextMenu.contains(e.target)) {
                contextMenu.classList.remove('active');
            }
        });
        
        // Context menu item handlers
        document.getElementById('contextMenuOpen')?.addEventListener('click', () => {
            if (this.contextMenuThreadId) {
                this.loadThread(this.contextMenuThreadId);
            }
            contextMenu.classList.remove('active');
        });
        
        document.getElementById('contextMenuMoveToProject')?.addEventListener('click', () => {
            if (this.contextMenuThreadId) {
                this.showMoveToProjectModal(this.contextMenuThreadId);
            }
            contextMenu.classList.remove('active');
        });
        
        document.getElementById('contextMenuDelete')?.addEventListener('click', () => {
            if (this.contextMenuThreadId) {
                this.deleteConversation(this.contextMenuThreadId);
            }
            contextMenu.classList.remove('active');
        });
    }
    
    showConversationContextMenu(event, threadId) {
        event.preventDefault();
        event.stopPropagation();
        
        this.contextMenuThreadId = threadId;
        
        const contextMenu = document.getElementById('conversationContextMenu');
        if (!contextMenu) return;
        
        // Position the menu
        const x = event.clientX;
        const y = event.clientY;
        
        // Make sure menu doesn't go off screen
        const menuWidth = 180;
        const menuHeight = 120;
        const windowWidth = window.innerWidth;
        const windowHeight = window.innerHeight;
        
        let posX = x;
        let posY = y;
        
        if (x + menuWidth > windowWidth) {
            posX = windowWidth - menuWidth - 10;
        }
        if (y + menuHeight > windowHeight) {
            posY = windowHeight - menuHeight - 10;
        }
        
        contextMenu.style.left = `${posX}px`;
        contextMenu.style.top = `${posY}px`;
        contextMenu.classList.add('active');
    }
    
    showMoveToProjectModal(threadId) {
        const modal = document.getElementById('moveToProjectModal');
        if (!modal) return;
        
        document.getElementById('moveThreadId').value = threadId;
        
        // Find current project for this thread
        const conversation = this.allConversations.find(c => c.thread_id === threadId);
        const currentProjectId = conversation?.primary_project_id;
        
        // Build project list
        const listContainer = document.getElementById('moveProjectList');
        let html = `
            <div class="move-project-unassign ${currentProjectId === null ? 'selected' : ''}" 
                 data-project-id="null"
                 onclick="window.syntaxPrimeChat.selectMoveProject(null)">
                Remove from project
            </div>
        `;
        
        this.projects.forEach(project => {
            const isSelected = currentProjectId === project.id;
            html += `
                <div class="move-project-item ${isSelected ? 'selected' : ''}" 
                     data-project-id="${project.id}"
                     onclick="window.syntaxPrimeChat.selectMoveProject(${project.id})">
                    <div class="project-color-dot" style="background: ${project.color || '#7b61ff'};"></div>
                    <span class="project-icon">${project.icon || '📁'}</span>
                    <span class="project-name">${project.display_name || project.name}</span>
                </div>
            `;
        });
        
        listContainer.innerHTML = html;
        
        // Enable/disable confirm button based on selection
        document.getElementById('confirmMoveToProject').disabled = false;
        
        // Show modal
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('active'), 10);
    }
    
    selectMoveProject(projectId) {
        // Update UI selection
        const items = document.querySelectorAll('#moveProjectList .move-project-item, #moveProjectList .move-project-unassign');
        items.forEach(item => {
            const itemProjectId = item.dataset.projectId === 'null' ? null : parseInt(item.dataset.projectId);
            item.classList.toggle('selected', itemProjectId === projectId);
        });
        
        // Store selection
        this._selectedMoveProjectId = projectId;
        
        // Enable confirm button
        document.getElementById('confirmMoveToProject').disabled = false;
    }
    
    async moveThreadToProject() {
        const threadId = document.getElementById('moveThreadId').value;
        const projectId = this._selectedMoveProjectId;
        
        try {
            await this.apiCall(`/ai/projects/threads/${threadId}/assign`, 'PUT', {
                project_id: projectId
            });
            
            this.showToast('✅ Conversation moved!', 'success');
            this.hideModal(document.getElementById('moveToProjectModal'));
            
            // Reload data
            await this.loadProjects();
            await this.loadConversations();
            
        } catch (error) {
            console.error('Failed to move conversation:', error);
            this.showToast('❌ Failed to move conversation', 'error');
        }
    }
    
    async deleteConversation(threadId) {
        if (!confirm('Are you sure you want to delete this conversation?')) {
            return;
        }
        
        try {
            await this.apiCall(`/ai/conversations/${threadId}`, 'DELETE');
            
            this.showToast('✅ Conversation deleted', 'success');
            
            // If this was the current conversation, start a new one
            if (this.currentThreadId === threadId) {
                this.startNewChat();
            }
            
            // Reload conversations
            await this.loadConversations();
            
        } catch (error) {
            console.error('Failed to delete conversation:', error);
            this.showToast('❌ Failed to delete conversation', 'error');
        }
    }
    
    async loadConversations() {
        try {
            const response = await this.apiCall('/ai/conversations?limit=300', 'GET');
            
            if (response && response.conversations) {
                // Store all conversations for filtering
                this.allConversations = response.conversations;
                
                // Render filtered or all based on selected project
                if (this.selectedProjectId) {
                    this.filterConversationsByProject(this.selectedProjectId);
                } else {
                    this.renderConversations(response.conversations);
                }
            }
        } catch (error) {
            console.error('Failed to load conversations:', error);
        }
    }
    
    renderConversations(conversations) {
        const sidebar = document.querySelector('.conversations-list');
        
        if (!sidebar) {
            console.error('Conversations sidebar not found');
            return;
        }
        
        if (conversations.length === 0) {
            sidebar.innerHTML = '<div class="no-conversations">No conversations yet</div>';
            return;
        }
        
        sidebar.innerHTML = conversations.map(conv => {
            // Find project for this conversation
            const project = conv.primary_project_id ? this.projects.find(p => p.id === conv.primary_project_id) : null;
            const projectBadge = project ? `
                <div class="conversation-project-badge" style="background: ${project.color}22; border: 1px solid ${project.color}44;">
                    <span class="project-badge-icon">${project.icon || '📁'}</span>
                    <span class="project-badge-name">${project.display_name || project.name}</span>
                </div>
            ` : '';
            
            return `
                <div class="conversation-item ${conv.thread_id === this.currentThreadId ? 'active' : ''}" 
                     data-thread-id="${conv.thread_id}" 
                     onclick="window.syntaxPrimeChat.loadThread('${conv.thread_id}')"
                     oncontextmenu="window.syntaxPrimeChat.showConversationContextMenu(event, '${conv.thread_id}')">
                    <div class="conversation-title">${conv.title || 'Untitled'}</div>
                    <div class="conversation-meta">
                        <span>${conv.message_count || 0} messages</span>
                        <span>${this.formatDate(conv.last_message_at)}</span>
                    </div>
                    ${projectBadge}
                    <button class="conversation-menu-btn" onclick="event.stopPropagation(); window.syntaxPrimeChat.showConversationContextMenu(event, '${conv.thread_id}');" title="More options">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="1"/>
                            <circle cx="12" cy="5" r="1"/>
                            <circle cx="12" cy="19" r="1"/>
                        </svg>
                    </button>
                </div>
            `;
        }).join('');
    }
    
    async loadThread(threadId) {
        try {
            this.currentThreadId = threadId;
            
            // Get messages for this thread
            const response = await this.apiCall(`/ai/conversations/${threadId}`, 'GET');
            
            if (!response || !response.messages) {
                this.showToast('❌ Failed to load conversation', 'error');
                return;
            }
            
            // Clear current messages
            const messagesContainer = document.getElementById('chatMessages');
            const welcomeMessage = messagesContainer.querySelector('.welcome-message');
            if (welcomeMessage) welcomeMessage.remove();
            
            messagesContainer.innerHTML = '';
            
            // Render message history
            response.messages.forEach(msg => {
                this.addMessage(msg.role, msg.content, {
                    messageId: msg.message_id,
                    personality: msg.personality_id,
                    responseTime: msg.response_time_ms
                });
            });
            
            // Update sidebar active state
            document.querySelectorAll('.conversation-item').forEach(item => {
                item.classList.toggle('active', item.dataset.threadId === threadId);
            });
            
            // Show gesture video for active conversation
            this.showGestureVideo();
            
            console.log(`Loaded thread: ${threadId}`);
            
        } catch (error) {
            console.error('Failed to load thread:', error);
            this.showToast('❌ Failed to load conversation', 'error');
        }
    }
    
    formatDate(dateString) {
        if (!dateString) return '';
        
        const date = new Date(dateString);
        const now = new Date();
        const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
        
        if (diffDays === 0) {
            return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
        } else if (diffDays === 1) {
            return 'Yesterday';
        } else if (diffDays < 7) {
            return date.toLocaleDateString('en-US', { weekday: 'short' });
        } else {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
    }
    
    // === File Upload Handling ===
    setupDragAndDrop() {
        const chatContainer = document.querySelector('.chat-container');
        const dragOverlay = document.getElementById('dragOverlay');
        
        if (!chatContainer || !dragOverlay) return;
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            chatContainer.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });
        
        chatContainer.addEventListener('dragenter', () => {
            dragOverlay.style.display = 'flex';
        });
        
        dragOverlay.addEventListener('dragleave', (e) => {
            if (e.target === dragOverlay) {
                dragOverlay.style.display = 'none';
            }
        });
        
        dragOverlay.addEventListener('drop', (e) => {
            dragOverlay.style.display = 'none';
            const files = e.dataTransfer.files;
            this.handleFiles(files);
        });
    }
    
    handleFileSelect(event) {
        const files = event.target.files;
        this.handleFiles(files);
    }
    
    handleFiles(files) {
        const maxSize = 10 * 1024 * 1024; // 10MB
        const allowedTypes = [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'application/pdf', 'text/plain', 'text/markdown', 'text/csv',
            'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'text/x-python', 'application/x-python-code'
        ];
        
        for (const file of files) {
            // Check file size
            if (file.size > maxSize) {
                this.showToast(`❌ ${file.name} is too large (max 10MB)`, 'error');
                continue;
            }
            
            // Check file type
            const isAllowed = allowedTypes.includes(file.type) ||
                              file.name.endsWith('.py') ||
                              file.name.endsWith('.md');
            
            if (!isAllowed) {
                this.showToast(`❌ ${file.name} type not supported`, 'error');
                continue;
            }
            
            // Add to uploaded files
            this.uploadedFiles.push({
                file: file,
                name: file.name,
                type: file.type,
                size: file.size
            });
        }
        
        this.renderUploadedFiles();
        this.handleInputChange();
    }
    
    renderUploadedFiles() {
        const fileUploadArea = document.getElementById('fileUploadArea');
        const uploadedFilesContainer = document.getElementById('uploadedFiles');
        
        if (this.uploadedFiles.length === 0) {
            fileUploadArea.style.display = 'none';
            return;
        }
        
        fileUploadArea.style.display = 'block';
        uploadedFilesContainer.innerHTML = this.uploadedFiles.map((file, index) => `
            <div class="uploaded-file">
                <span>${this.getFileIcon(file.type)} ${file.name}</span>
                <button class="file-remove" onclick="window.syntaxPrimeChat.removeFile(${index})">×</button>
            </div>
        `).join('');
    }
    
    getFileIcon(type) {
        if (type.startsWith('image/')) return '🖼️';
        if (type === 'application/pdf') return '📄';
        if (type.includes('word')) return '📝';
        if (type.includes('excel') || type.includes('spreadsheet')) return '📊';
        if (type.includes('python') || type === 'text/x-python') return '🐍';
        return '📎';
    }
    
    removeFile(index) {
        this.uploadedFiles.splice(index, 1);
        this.renderUploadedFiles();
        this.handleInputChange();
    }
    
    clearUploadedFiles() {
        this.uploadedFiles = [];
        this.renderUploadedFiles();
    }
    
    // === Bookmark Functions ===
    showBookmarkModal() {
        const modal = document.getElementById('bookmarkModal');
        if (modal) {
            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('active'), 10);
            
            // Focus the input
            const nameInput = document.getElementById('bookmarkName');
            if (nameInput) {
                nameInput.value = '';
                nameInput.focus();
            }
        }
    }
    
    showDriveModal() {
        const modal = document.getElementById('driveModal');
        if (modal) {
            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('active'), 10);
            
            // Focus the input
            const nameInput = document.getElementById('driveDocName');
            if (nameInput) {
                nameInput.value = '';
                nameInput.focus();
            }
        }
    }
    
    async saveBookmark() {
        const nameInput = document.getElementById('bookmarkName');
        const bookmarkName = nameInput?.value.trim();
        
        if (!bookmarkName) {
            this.showToast('❌ Please enter a bookmark name', 'error');
            return;
        }
        
        if (!this.bookmarkToCreate) {
            this.showToast('❌ No message to bookmark', 'error');
            return;
        }
        
        try {
            const response = await this.apiCall('/ai/bookmarks', 'POST', {
                message_id: this.bookmarkToCreate.messageId,
                bookmark_name: bookmarkName
            });
            
            if (response && response.success) {
                this.showToast('✅ Bookmark saved!', 'success');
                this.hideModal(document.getElementById('bookmarkModal'));
                this.bookmarkToCreate = null;
                
                // Reload bookmarks
                await this.loadBookmarks();
            }
        } catch (error) {
            console.error('Error saving bookmark:', error);
            this.showToast('❌ Failed to save bookmark', 'error');
        }
    }
    
    async saveDriveDoc() {
        const nameInput = document.getElementById('driveDocName');
        const docName = nameInput?.value.trim();
        
        if (!docName) {
            this.showToast('❌ Please enter a document name', 'error');
            return;
        }
        
        if (!this.driveDocToCreate) {
            this.showToast('❌ No content to save', 'error');
            return;
        }
        
        try {
            console.log('💾 Creating Drive document:', docName);
            
            const requestData = {
                title: docName,
                content: this.driveDocToCreate.content,
                chat_thread_id: this.currentThreadId || null
            };
            
            console.log('📤 Calling Drive API...');
            const response = await this.apiCall('/google/drive/document', 'POST', requestData);
            console.log('📥 Drive API response:', response);
            
            if (response && response.success) {
                this.showToast('✅ Document created!', 'success');
                
                // Show link to open document
                if (response.document && response.document.url) {
                    setTimeout(() => {
                        this.showToast(`📄 <a href="${response.document.url}" target="_blank" style="color: white; text-decoration: underline;">Open in Google Docs</a>`, 'info');
                    }, 1500);
                }
            }
            
            this.hideModal(document.getElementById('driveModal'));
            document.getElementById('driveDocName').value = '';
            this.driveDocToCreate = null;
            
        } catch (error) {
            console.error('❌ Error creating Drive doc:', error);
            this.showToast('❌ Failed to create document. Make sure Google Drive is connected.', 'error');
        }
    }
    
    copyMessage(messageId) {
        try {
            // Find the message element by messageId
            const messageElements = document.querySelectorAll('.message.assistant');
            let messageText = '';
            
            // Get the text from the message bubble
            for (const msgEl of messageElements) {
                const bubble = msgEl.querySelector('.message-bubble');
                if (bubble) {
                    messageText = bubble.innerText || bubble.textContent;
                    // Just copy the last assistant message for now
                    // (proper messageId tracking would require more changes)
                }
            }
            
            if (messageText) {
                navigator.clipboard.writeText(messageText).then(() => {
                    this.showToast('✅ Copied to clipboard!', 'success');
                }).catch(err => {
                    this.showToast('❌ Copy failed', 'error');
                });
            }
        } catch (error) {
            console.error('Copy failed:', error);
            this.showToast('❌ Copy failed', 'error');
        }
    }
    
    async loadBookmarks() {
        try {
            const response = await this.apiCall('/ai/bookmarks?limit=50', 'GET');
            
            if (response && response.bookmarks) {
                this.renderBookmarks(response.bookmarks);
            }
        } catch (error) {
            console.error('Failed to load bookmarks:', error);
        }
    }
    
    renderBookmarks(bookmarks) {
        const bookmarksList = document.querySelector('.bookmarks-list');
        const bookmarkCount = document.getElementById('bookmarkCount');
        
        if (!bookmarksList) {
            console.error('Bookmarks list not found');
            return;
        }
        
        // Update count
        if (bookmarkCount) {
            bookmarkCount.textContent = bookmarks.length;
        }
        
        if (bookmarks.length === 0) {
            bookmarksList.innerHTML = `
                <div class="no-bookmarks">
                    <p>No bookmarks yet</p>
                    <small>Use "Remember This" to create your first bookmark</small>
                </div>
            `;
            return;
        }
        
        bookmarksList.innerHTML = bookmarks.map(bookmark => `
            <div class="bookmark-item" onclick="window.syntaxPrimeChat.loadBookmarkedMessage('${bookmark.message_id}')">
                <div class="bookmark-name">${bookmark.bookmark_name}</div>
                <div class="bookmark-date">${this.formatDate(bookmark.created_at)}</div>
            </div>
        `).join('');
    }
    
    async submitFeedback(messageId, feedbackType) {
        try {
            console.log('Feedback submitted:', messageId, feedbackType);
            
            const response = await this.apiCall('/ai/feedback', 'POST', {
                message_id: messageId,
                feedback_type: feedbackType
            });
            
            if (response && response.message) {
                this.showToast(response.message, 'success');
            }
        } catch (error) {
            console.error('Error submitting feedback:', error);
            this.showToast('❌ Failed to submit feedback', 'error');
        }
    }
    
    rememberMessage(messageId) {
        console.log('Remember message:', messageId);
        
        // Store which message we're bookmarking
        this.bookmarkToCreate = {
            messageId: messageId
        };
        
        this.showBookmarkModal();
    }
    
    copyToDrive(messageId) {
        console.log('💾 Copy to Drive:', messageId);
        
        // Get the message element and retrieve raw markdown
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        const content = messageElement ? messageElement.getAttribute('data-raw-markdown') : null;
        
        if (!content) {
            this.showToast('❌ Could not find message content', 'error');
            return;
        }
        
        console.log('📝 Content type:', typeof content);
        console.log('📝 Content preview (first 200 chars):', content.substring(0, 200));
        console.log('📝 Content includes italic markers:', content.includes('*'));
        console.log('📝 Content includes bold markers:', content.includes('**'));
        
        // Store which message we're copying (same pattern as bookmarks)
        this.driveDocToCreate = {
            messageId: messageId,
            content: content
        };
        
        this.showDriveModal();
    }
    
    async loadBookmarkedMessage(messageId) {
        try {
            // For now, just show a toast - full implementation would load the thread
            this.showToast('📌 Loading bookmarked message...', 'info');
            
            // You could implement thread loading here
            console.log('Load bookmarked message:', messageId);
        } catch (error) {
            console.error('Error loading bookmarked message:', error);
        }
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
