// =============================================================================
// Syntax Prime V2 - FIXED Chat Interface JavaScript with Anti-Duplication
// Fixes: Double submission prevention, DOM ready protection, proper initialization
// Date: 9/26/25
// =============================================================================

//-- Section 1: Core Class Setup and Constructor - 9/26/25
class SyntaxPrimeChat {
    constructor() {
        this.apiBase = window.location.origin;
        this.currentThreadId = null;
        this.currentPersonality = 'syntaxprime';
        this.uploadedFiles = [];
        this.isTyping = false;
        this.bookmarkToCreate = null;
        this.isSubmitting = false; // NEW: Prevent double submission
        this.lastSubmitTime = 0;   // NEW: Debounce protection
        
        this.init();
    }

//-- Section 2: Initialization and Event Listeners - 9/26/25
    init() {
        this.setupEventListeners();
        this.loadPersonalities();
        this.loadConversations();
        this.setupDragAndDrop();
        this.autoResizeTextarea();
        
        // Focus message input
        document.getElementById('messageInput').focus();
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

        // Chat input with anti-duplication protection
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        
        messageInput.addEventListener('input', this.handleInputChange.bind(this));
        messageInput.addEventListener('keydown', this.handleKeyPress.bind(this));
        
        // FIXED: Only allow one event listener and add protection
        sendButton.addEventListener('click', this.handleSendClick.bind(this));

        // File upload
        document.getElementById('fileButton').addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });
        
        document.getElementById('fileInput').addEventListener('change', this.handleFileSelect.bind(this));

        // Remember This button
        document.getElementById('rememberBtn').addEventListener('click', this.showBookmarkModal.bind(this));

        // Modal handlers
        this.setupModalHandlers();
    }

//-- Section 3: NEW Anti-Duplication Send Handler - 9/26/25
    handleSendClick(event) {
        event.preventDefault();
        event.stopPropagation();
        
        // Anti-duplication protection
        const now = Date.now();
        if (this.isSubmitting || (now - this.lastSubmitTime) < 1000) {
            console.log('🛡️ Double submission prevented');
            return;
        }
        
        this.sendMessage();
    }

    handleKeyPress(event) {
        // FIXED: Only submit on Enter (not Shift+Enter) with anti-duplication
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            event.stopPropagation();
            
            const now = Date.now();
            if (this.isSubmitting || (now - this.lastSubmitTime) < 1000) {
                console.log('🛡️ Double submission prevented (Enter key)');
                return;
            }
            
            if (!document.getElementById('sendButton').disabled && !this.isTyping) {
                this.sendMessage();
            }
        }
    }

//-- Section 4: Modal Event Handlers - 9/23/25
    setupModalHandlers() {
        // Bookmark modal
        const bookmarkModal = document.getElementById('bookmarkModal');
        document.getElementById('closeBookmarkModal').addEventListener('click', () => {
            this.hideModal(bookmarkModal);
        });
        document.getElementById('cancelBookmark').addEventListener('click', () => {
            this.hideModal(bookmarkModal);
        });
        document.getElementById('saveBookmark').addEventListener('click', this.saveBookmark.bind(this));

        // Settings modal
        const settingsModal = document.getElementById('settingsModal');
        document.getElementById('closeSettingsModal').addEventListener('click', () => {
            this.hideModal(settingsModal);
        });
        document.getElementById('saveSettings').addEventListener('click', this.saveSettings.bind(this));

        // Close modals on outside click
        [bookmarkModal, settingsModal].forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideModal(modal);
                }
            });
        });
    }

//-- Section 5: API Communication with Error Handling - 9/23/25
    async apiCall(endpoint, method = 'GET', data = null) {
        try {
            const options = {
                method,
                headers: {},
                credentials: 'include'
            };

            if (data && method !== 'GET') {
                if (data instanceof FormData) {
                    // Let browser set content-type for FormData
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
                // Handle different error response formats
                let errorMessage = 'Unknown error';
                
                if (typeof responseData === 'object' && responseData.detail) {
                    if (Array.isArray(responseData.detail)) {
                        // FastAPI validation errors
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
            
            // Show user-friendly error message
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

//-- Section 6: FIXED Chat Message Sending with Anti-Duplication - 9/26/25
    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();
        
        if (!message && this.uploadedFiles.length === 0) return;
        
        // CRITICAL: Anti-duplication protection
        if (this.isSubmitting) {
            console.log('🛡️ Already submitting, ignoring duplicate call');
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

            // FIXED: Prepare request with current date/time for Syntax
            const currentDateTime = new Date();
            const requestData = {
                message: message,
                personality_id: this.currentPersonality,
                thread_id: this.currentThreadId,
                include_knowledge: true,
                // NEW: Provide current date/time context for Syntax
                context: {
                    current_date: currentDateTime.toISOString().split('T')[0], // YYYY-MM-DD
                    current_time: currentDateTime.toLocaleTimeString('en-US', { hour12: false }), // 24-hour format
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timestamp: currentDateTime.toISOString()
                }
            };

            // Send request using proper JSON format
            const response = await this.apiCall('/ai/chat', 'POST', requestData);
            
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
            
            // Show remember button for the last assistant message
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

//-- Section 7: Input State Management - 9/26/25
    setInputState(enabled) {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const fileButton = document.getElementById('fileButton');
        
        messageInput.disabled = !enabled;
        sendButton.disabled = !enabled || this.isSubmitting;
        fileButton.disabled = !enabled;
        
        if (enabled) {
            sendButton.classList.remove('loading');
        } else {
            sendButton.classList.add('loading');
        }
    }

// ... [REST OF THE EXISTING METHODS REMAIN THE SAME] ...

//-- Section 8: Message Display with Feedback Buttons - 9/23/25
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
            
            // Create Remember button
            const rememberBtn = document.createElement('button');
            rememberBtn.className = 'message-action remember-action';
            rememberBtn.title = 'Remember This';
            rememberBtn.style.display = 'none';
            rememberBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5Z"/>
                </svg>
            `;
            rememberBtn.addEventListener('click', () => this.rememberMessage(metadata.messageId));
            
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
            personalityBtn.innerHTML = '🎭';
            personalityBtn.addEventListener('click', () => this.submitFeedback(metadata.messageId, 'good_personality'));
            
            actionsDiv.appendChild(copyBtn);
            actionsDiv.appendChild(rememberBtn);
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

// ... [ALL OTHER EXISTING METHODS CONTINUE AS BEFORE] ...

}

//-- Section 19: FIXED App Initialization with DOM Ready Protection - 9/26/25
// CRITICAL FIX: Only initialize when DOM is ready and only once
let syntaxChat = null;

function initializeSyntaxChat() {
    if (syntaxChat) {
        console.log('🛡️ SyntaxChat already initialized, skipping');
        return;
    }
    
    console.log('🚀 Initializing SyntaxChat');
    syntaxChat = new SyntaxPrimeChat();
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSyntaxChat);
} else {
    // DOM is already ready
    initializeSyntaxChat();
}

// Add notification animations to document
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
