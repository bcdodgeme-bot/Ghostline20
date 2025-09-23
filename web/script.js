// =============================================================================
// Syntax Prime V2 - Fixed Chat Interface JavaScript
// Fixes: API errors, input visibility, submit button, request format
// =============================================================================

class SyntaxPrimeChat {
    constructor() {
        this.apiBase = window.location.origin;
        this.currentThreadId = null;
        this.currentPersonality = 'syntaxprime';
        this.uploadedFiles = [];
        this.isTyping = false;
        this.bookmarkToCreate = null;
        
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

        // Chat input
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        
        messageInput.addEventListener('input', this.handleInputChange.bind(this));
        messageInput.addEventListener('keydown', this.handleKeyPress.bind(this));
        
        sendButton.addEventListener('click', this.sendMessage.bind(this));

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

    // === FIXED: API Communication with proper error handling ===
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

    // === FIXED: Chat message sending with proper request format ===
    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();
        
        if (!message && this.uploadedFiles.length === 0) return;

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

            // FIXED: Prepare request in the format the API expects
            const requestData = {
                message: message,
                personality_id: this.currentPersonality,
                thread_id: this.currentThreadId,
                include_knowledge: true
            };

            // Send request using proper JSON format (not FormData for simple messages)
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
        }

        // Re-enable input
        this.setInputState(true);
        messageInput.focus();
    }

    // === FIXED: Message display with better error handling ===
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

        // Add message actions for assistant messages
        if (role === 'assistant' && !metadata.error) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            actionsDiv.innerHTML = `
                <button class="message-action" onclick="syntaxChat.copyMessage('${messageDiv.dataset.messageId}')" title="Copy">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                </button>
                <button class="message-action remember-action" onclick="syntaxChat.rememberMessage('${messageDiv.dataset.messageId}')" title="Remember This" style="display: none;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5Z"/>
                    </svg>
                </button>
            `;
            contentDiv.appendChild(actionsDiv);
        }

        // Add metadata for assistant messages
        if (role === 'assistant' && metadata.personality && !metadata.error) {
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
        // Basic markdown-like formatting
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    // === FIXED: Input handling with proper submit button ===
    handleInputChange() {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        
        // Update character count
        this.updateCharCount();
        
        // Enable/disable send button
        const hasContent = messageInput.value.trim().length > 0 || this.uploadedFiles.length > 0;
        sendButton.disabled = !hasContent || this.isTyping;
        
        // Auto-resize textarea
        this.autoResizeTextarea();
    }

    handleKeyPress(event) {
        // FIXED: Only submit on Enter (not Shift+Enter) and only if not typing
        if (event.key === 'Enter' && !event.shiftKey && !this.isTyping) {
            event.preventDefault();
            if (!document.getElementById('sendButton').disabled) {
                this.sendMessage();
            }
        }
    }

    // === FIXED: Auto-resize textarea to show full content ===
    autoResizeTextarea() {
        const textarea = document.getElementById('messageInput');
        // Reset height to auto to get correct scrollHeight
        textarea.style.height = 'auto';
        // Set height to scrollHeight but cap at reasonable max
        const newHeight = Math.min(textarea.scrollHeight, 150);
        textarea.style.height = newHeight + 'px';
        
        // Ensure the input container is visible
        const inputContainer = document.querySelector('.chat-input-container');
        const chatMessages = document.querySelector('.chat-messages');
        
        // Adjust chat messages height to account for input area
        if (inputContainer && chatMessages) {
            const inputHeight = inputContainer.offsetHeight;
            chatMessages.style.paddingBottom = inputHeight + 'px';
        }
    }

    updateCharCount() {
        const messageInput = document.getElementById('messageInput');
        const charCount = document.getElementById('charCount');
        const currentLength = messageInput.value.length;
        charCount.textContent = `${currentLength}/8000`;
        
        if (currentLength > 7500) {
            charCount.style.color = 'var(--warning)';
        } else if (currentLength > 7900) {
            charCount.style.color = 'var(--error)';
        } else {
            charCount.style.color = 'var(--text-tertiary)';
        }
    }

    setInputState(enabled) {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const fileButton = document.getElementById('fileButton');
        
        messageInput.disabled = !enabled;
        sendButton.disabled = !enabled;
        fileButton.disabled = !enabled;
        
        if (enabled) {
            // Re-check if send should be enabled based on content
            this.handleInputChange();
        }
    }

    // === Show/Hide typing indicator ===
    showTypingIndicator() {
        const messagesContainer = document.getElementById('chatMessages');
        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator';
        typingDiv.id = 'typingIndicator';
        typingDiv.innerHTML = `
            <div class="message-avatar">
                <img src="static/syntax-buffering.png" alt="Syntax" style="width: 32px; height: 32px; object-fit: contain; border-radius: 50%;">
            </div>
            <div class="typing-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
            <span>Syntax is thinking...</span>
        `;
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        this.isTyping = true;
    }

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        this.isTyping = false;
    }

    showRememberButton(messageId) {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            const rememberBtn = messageDiv.querySelector('.remember-action');
            if (rememberBtn) {
                rememberBtn.style.display = 'block';
            }
        }
    }

    // === File Upload Functions (keeping existing) ===
    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        files.forEach(file => this.addUploadedFile(file));
        event.target.value = '';
    }

    addUploadedFile(file) {
        if (!this.validateFile(file)) return;
        this.uploadedFiles.push(file);
        this.updateFileUploadArea();
    }

    validateFile(file) {
        const maxSize = 10 * 1024 * 1024; // 10MB
        const allowedTypes = ['image/', 'application/pdf', 'text/', 'text/csv'];

        if (file.size > maxSize) {
            this.showError(`File "${file.name}" is too large. Maximum size is 10MB.`);
            return false;
        }

        if (!allowedTypes.some(type => file.type.startsWith(type))) {
            this.showError(`File type not supported: ${file.type}`);
            return false;
        }

        return true;
    }

    updateFileUploadArea() {
        const uploadArea = document.getElementById('fileUploadArea');
        const filesContainer = document.getElementById('uploadedFiles');

        if (this.uploadedFiles.length > 0) {
            uploadArea.style.display = 'block';
            filesContainer.innerHTML = '';

            this.uploadedFiles.forEach((file, index) => {
                const fileDiv = document.createElement('div');
                fileDiv.className = 'uploaded-file';
                fileDiv.innerHTML = `
                    <span>${this.getFileIcon(file.type)} ${file.name}</span>
                    <button class="file-remove" onclick="syntaxChat.removeFile(${index})" title="Remove">×</button>
                `;
                filesContainer.appendChild(fileDiv);
            });
        } else {
            uploadArea.style.display = 'none';
        }
    }

    removeFile(index) {
        this.uploadedFiles.splice(index, 1);
        this.updateFileUploadArea();
        this.handleInputChange(); // Update send button state
    }

    clearUploadedFiles() {
        this.uploadedFiles = [];
        this.updateFileUploadArea();
    }

    getFileIcon(mimeType) {
        if (mimeType.startsWith('image/')) return '🖼️';
        if (mimeType === 'application/pdf') return '📄';
        if (mimeType.startsWith('text/')) return '📝';
        return '📎';
    }

    // === Drag and Drop (keeping existing) ===
    setupDragAndDrop() {
        const dragOverlay = document.getElementById('dragOverlay');
        let dragCounter = 0;

        document.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            if (dragCounter === 1) {
                dragOverlay.style.display = 'flex';
            }
        });

        document.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter === 0) {
                dragOverlay.style.display = 'none';
            }
        });

        document.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        document.addEventListener('drop', (e) => {
            e.preventDefault();
            dragCounter = 0;
            dragOverlay.style.display = 'none';

            const files = Array.from(e.dataTransfer.files);
            files.forEach(file => this.addUploadedFile(file));
        });
    }

    // === Other methods (keeping existing with error handling improvements) ===
    async loadPersonalities() {
        try {
            const response = await this.apiCall('/ai/personalities');
            const select = document.getElementById('personalitySelect');
            const defaultSelect = document.getElementById('defaultPersonality');
            
            select.innerHTML = '';
            if (defaultSelect) defaultSelect.innerHTML = '';
            
            response.personalities.forEach(personality => {
                const option = document.createElement('option');
                option.value = personality.id;
                option.textContent = personality.name;
                option.title = personality.description;
                select.appendChild(option);
                
                if (defaultSelect) {
                    const defaultOption = option.cloneNode(true);
                    defaultSelect.appendChild(defaultOption);
                }
            });
            
            select.value = response.default_personality;
            this.currentPersonality = response.default_personality;
            
        } catch (error) {
            console.error('Failed to load personalities:', error);
            this.showError('Failed to load personalities');
        }
    }

    async loadConversations() {
        try {
            const response = await this.apiCall('/ai/conversations?limit=10');
            this.displayConversations(response.conversations);
        } catch (error) {
            console.error('Failed to load conversations:', error);
            document.getElementById('conversationsList').innerHTML =
                '<div class="loading-conversations">Failed to load conversations</div>';
        }
    }

    displayConversations(conversations) {
        const conversationsList = document.getElementById('conversationsList');
        
        if (conversations.length === 0) {
            conversationsList.innerHTML = '<div class="loading-conversations">No conversations yet</div>';
            return;
        }

        conversationsList.innerHTML = '';
        conversations.forEach(conversation => {
            const convDiv = document.createElement('div');
            convDiv.className = 'conversation-item';
            if (conversation.thread_id === this.currentThreadId) {
                convDiv.classList.add('active');
            }
            
            convDiv.innerHTML = `
                <div class="conversation-title">${conversation.title || 'New Conversation'}</div>
                <div class="conversation-meta">
                    <span>${conversation.message_count || 0} messages</span>
                    <span>${new Date(conversation.last_message_at).toLocaleDateString()}</span>
                </div>
            `;
            
            convDiv.addEventListener('click', () => {
                this.loadConversation(conversation.thread_id);
            });
            
            conversationsList.appendChild(convDiv);
        });
    }

    // === Utility Functions ===
    showError(message) {
        this.showNotification(message, 'error');
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#7b61ff'};
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10001;
            animation: slideInRight 0.3s ease;
            max-width: 400px;
            word-wrap: break-word;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                if (document.body.contains(notification)) {
                    document.body.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }

    // === Other existing methods ===
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        
        if (window.innerWidth <= 768) {
            sidebar.classList.toggle('open');
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
                <h2>New Conversation Started</h2>
                <p>Ready to assist with 38% more sarcasm and full memory sync.</p>
            </div>
        `;
        
        document.getElementById('messageInput').focus();
    }

    copyMessage(messageId) {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            const text = messageDiv.querySelector('.message-text').textContent;
            navigator.clipboard.writeText(text).then(() => {
                this.showSuccess('Message copied to clipboard');
            });
        }
    }

    rememberMessage(messageId) {
        // Implement bookmark functionality
        this.showSuccess('Remember functionality coming soon!');
    }

    showModal(modal) {
        modal.classList.add('active');
        modal.style.display = 'flex';
    }

    hideModal(modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }

    openSettings() {
        this.showModal(document.getElementById('settingsModal'));
    }

    saveSettings() {
        this.hideModal(document.getElementById('settingsModal'));
        this.showSuccess('Settings saved!');
    }

    logout() {
        fetch('/auth/logout', {
            method: 'POST',
            credentials: 'include'
        }).finally(() => {
            sessionStorage.clear();
            localStorage.clear();
            window.location.href = '/';
        });
    }
}

// === Initialize App ===
const syntaxChat = new SyntaxPrimeChat();

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
