//=============================================================================
// Syntax Prime V2 - Chat Interface JavaScript (MERGED WORKING VERSION)
// Combines fixes from both versions with proper anti-duplication
// Date: 9/26/25 - Working sidebar + submit protection
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

        this.init();
    }

    // === Initialization ===
    init() {
        this.setupEventListeners();
        this.loadPersonalities();
        this.loadConversations();
        this.setupDragAndDrop();
        this.autoResizeTextarea();

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
        // Header controls
        document.getElementById('sidebarToggle').addEventListener('click', this.toggleSidebar.bind(this));
        document.getElementById('newChatBtn').addEventListener('click', this.startNewChat.bind(this));
        document.getElementById('settingsBtn').addEventListener('click', this.openSettings.bind(this));
        document.getElementById('logoutBtn').addEventListener('click', this.logout.bind(this));

        // Personality selector
        document.getElementById('personalitySelect').addEventListener('change', (e) => {
            this.currentPersonality = e.target.value;
            this.saveSettings();
        });

        // Chat input with enhanced anti-duplication
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');

        messageInput.addEventListener('input', this.handleInputChange.bind(this));
        messageInput.addEventListener('keydown', this.handleKeyPress.bind(this));
        
        // FIXED: Use the enhanced send handler from working version
        sendButton.addEventListener('click', this.handleSendClick.bind(this));

        // File upload - FIXED: Correct element IDs
        const fileButton = document.getElementById('fileButton');
        const fileInput = document.getElementById('fileInput');
        
        if (fileButton && fileInput) {
            fileButton.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', this.handleFileSelect.bind(this));
        }

        // Remember button
        const rememberBtn = document.getElementById('rememberBtn');
        if (rememberBtn) {
            rememberBtn.addEventListener('click', this.showBookmarkModal.bind(this));
        }

        // Modal handlers
        this.setupModalHandlers();
    }

    // ENHANCED: Anti-duplication send handler from working version
    handleSendClick(event) {
        event.preventDefault();
        event.stopPropagation();

        // Anti-duplication protection
        const now = Date.now();
        if (this.isSubmitting || (now - this.lastSubmitTime) < 1000) {
            console.log('⛔️ Double submission prevented');
            return;
        }

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

    // ENHANCED: Send message with working version improvements
    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();

        if (!message && this.uploadedFiles.length === 0) return;

        // CRITICAL: Anti-duplication protection
        if (this.isSubmitting) {
            console.log('⛔️ Already submitting, ignoring duplicate call');
            return;
        }

        this.isSubmitting = true;
        this.lastSubmitTime = Date.now();

        // Disable input while sending
        this.setInputState(false);

        // Add user message to chat
        this.addMessage('user', message, { files: this.uploadedFiles.slice() });

        // Clear input
        messageInput.value = '';
        this.updateCharCount();
        this.clearUploadedFiles();

        try {
            // Show typing indicator
            this.showTypingIndicator();

            // ENHANCED: Better datetime context from working version
            const currentDateTime = new Date();
            const requestData = {
                message: message,
                personality_id: this.currentPersonality,
                thread_id: this.currentThreadId,
                include_knowledge: true,
                // Enhanced context format
                context: {
                    current_date: currentDateTime.toISOString().split('T')[0],
                    current_time: currentDateTime.toLocaleTimeString('en-US', { hour12: false }),
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timestamp: currentDateTime.toISOString()
                }
            };

            console.log('📤 Sending request with context:', requestData.context);

            // Send request
            const response = await this.apiCall('/ai/chat', 'POST', requestData);

            console.log('📥 Received response:', response);

            // Update thread ID
            this.currentThreadId = response.thread_id;

            // Hide typing indicator
            this.hideTypingIndicator();

            // Add AI response
            this.addMessage('assistant', response.response, {
                messageId: response.message_id,
                personality: response.personality_used,
                responseTime: response.response_time_ms,
                knowledgeSources: response.knowledge_sources || []
            });

            // Show remember button
            this.showRememberButton(response.message_id);

        } catch (error) {
            this.hideTypingIndicator();
            this.addMessage('assistant', 'Sorry, I encountered an error. Please try again.', { error: true });
            console.error('Chat error:', error);
        } finally {
            // CRITICAL: Always re-enable input and reset submission flag
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

    // ENHANCED: Message display from working version with feedback buttons
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

            const personalityBtn = document.createElement('button');
            personalityBtn.className = 'message-action feedback-personality';
            personalityBtn.title = 'Good Personality';
            personalityBtn.innerHTML = '😄';
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
                        <span class="feature-icon">🔖</span>
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

// ENHANCED: Proper initialization with DOM ready protection
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

// Add notification animations
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
`;
document.head.appendChild(style);
