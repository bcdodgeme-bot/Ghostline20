// =============================================================================
// Syntax Prime V2 - Chat Interface JavaScript
// Handles chat, file uploads, bookmarks, and personality switching
// =============================================================================

class SyntaxPrimeChat {
    constructor() {
        this.apiBase = window.location.origin; // Assumes API is on same domain
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

    // === API Communication ===
    async apiCall(endpoint, method = 'GET', data = null) {
        try {
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include' // Include cookies for session authentication
            };

            if (data && method !== 'GET') {
                if (data instanceof FormData) {
                    delete options.headers['Content-Type']; // Let browser set it for FormData
                    options.body = data;
                } else {
                    options.body = JSON.stringify(data);
                }
            }

            const response = await fetch(`${this.apiBase}${endpoint}`, options);
            
            if (response.status === 401) {
                // Authentication failed - redirect to login
                this.logout();
                return;
            }
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            this.showError(`API Error: ${error.message}`);
            throw error;
        }
    }

    // === Authentication Functions ===
    async logout() {
        try {
            await fetch('/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });
        } catch (error) {
            console.error('Logout error:', error);
        }
        
        // Clear client-side storage
        sessionStorage.clear();
        localStorage.clear();
        
        // Redirect to login
        window.location.href = '/';
    }

    // === Chat Functions ===
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

            // Prepare request data
            const formData = new FormData();
            formData.append('message', message);
            formData.append('personality_id', this.currentPersonality);
            formData.append('thread_id', this.currentThreadId || '');
            formData.append('include_knowledge', 'true');

            // Add files
            this.uploadedFiles.forEach(file => {
                formData.append('files', file);
            });

            // Send to API
            const response = await this.apiCall('/ai/chat', 'POST', formData);
            
            // Update thread ID
            this.currentThreadId = response.thread_id;
            
            // Hide typing indicator
            this.hideTypingIndicator();
            
            // Add AI response
            this.addMessage('assistant', response.response, {
                messageId: response.message_id,
                personality: response.personality_used,
                responseTime: response.response_time_ms,
                knowledgeSources: response.knowledge_sources
            });
            
            // Show remember button for the last assistant message
            this.showRememberButton(response.message_id);
            
        } catch (error) {
            this.hideTypingIndicator();
            this.addMessage('assistant', 'Sorry, I encountered an error. Please try again.', { error: true });
        }

        // Re-enable input
        this.setInputState(true);
        messageInput.focus();
    }

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
            avatar.innerHTML = '👤'; // Keep user as person icon
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
        // Show the remember button for the specific message
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            const rememberBtn = messageDiv.querySelector('.remember-action');
            if (rememberBtn) {
                rememberBtn.style.display = 'block';
            }
        }
    }

    // === File Upload Functions ===
    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        files.forEach(file => this.addUploadedFile(file));
        event.target.value = ''; // Reset input
    }

    addUploadedFile(file) {
        // Validate file
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

    // === Drag and Drop ===
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

    // === Bookmark Functions ===
    async rememberMessage(messageId) {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageDiv) return;

        this.bookmarkToCreate = {
            messageId,
            content: messageDiv._messageContent || messageDiv.querySelector('.message-text').textContent
        };

        document.getElementById('bookmarkPreview').textContent =
            this.bookmarkToCreate.content.substring(0, 200) + '...';
        
        this.showModal(document.getElementById('bookmarkModal'));
        document.getElementById('bookmarkName').focus();
    }

    async saveBookmark() {
        const bookmarkName = document.getElementById('bookmarkName').value.trim();
        if (!bookmarkName || !this.bookmarkToCreate) return;

        try {
            await this.apiCall('/ai/bookmarks', 'POST', {
                message_id: this.bookmarkToCreate.messageId,
                bookmark_name: bookmarkName,
                thread_id: this.currentThreadId
            });

            this.hideModal(document.getElementById('bookmarkModal'));
            this.loadBookmarks();
            this.showSuccess(`Bookmark "${bookmarkName}" saved!`);
            
            // Clear form
            document.getElementById('bookmarkName').value = '';
            this.bookmarkToCreate = null;

        } catch (error) {
            this.showError('Failed to save bookmark');
        }
    }

    async loadBookmarks() {
        if (!this.currentThreadId) return;

        try {
            const response = await this.apiCall(`/ai/bookmarks/${this.currentThreadId}`);
            this.displayBookmarks(response.bookmarks);
            document.getElementById('bookmarkCount').textContent = response.total_bookmarks;
        } catch (error) {
            console.error('Failed to load bookmarks:', error);
        }
    }

    displayBookmarks(bookmarks) {
        const bookmarksList = document.getElementById('bookmarksList');
        
        if (bookmarks.length === 0) {
            bookmarksList.innerHTML = `
                <div class="no-bookmarks">
                    <p>No bookmarks yet</p>
                    <small>Use "Remember This" to create your first bookmark</small>
                </div>
            `;
            return;
        }

        bookmarksList.innerHTML = '';
        bookmarks.forEach(bookmark => {
            const bookmarkDiv = document.createElement('div');
            bookmarkDiv.className = 'bookmark-item';
            bookmarkDiv.innerHTML = `
                <div class="bookmark-name">${bookmark.bookmark_name}</div>
                <div class="bookmark-preview">${bookmark.preview}</div>
                <div class="bookmark-date">${new Date(bookmark.created_at).toLocaleDateString()}</div>
            `;
            
            bookmarkDiv.addEventListener('click', () => {
                this.jumpToBookmark(bookmark.original_message_id);
            });
            
            bookmarksList.appendChild(bookmarkDiv);
        });
    }

    jumpToBookmark(messageId) {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            messageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
            messageDiv.style.background = 'rgba(123, 97, 255, 0.2)';
            setTimeout(() => {
                messageDiv.style.background = '';
            }, 2000);
        }
    }

    // === Personality Functions ===
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
            
            // Set default
            select.value = response.default_personality;
            this.currentPersonality = response.default_personality;
            
        } catch (error) {
            console.error('Failed to load personalities:', error);
        }
    }

    // === Conversation Functions ===
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

    async loadConversation(threadId) {
        try {
            const response = await this.apiCall(`/ai/conversations/${threadId}/messages`);
            this.currentThreadId = threadId;
            
            // Clear current messages
            const messagesContainer = document.getElementById('chatMessages');
            messagesContainer.innerHTML = '';
            
            // Load messages
            response.messages.forEach(msg => {
                if (msg.role !== 'system') {
                    this.addMessage(msg.role, msg.content, {
                        messageId: msg.id,
                        timestamp: msg.timestamp
                    });
                }
            });
            
            // Update UI
            this.updateConversationUI();
            this.loadBookmarks();
            
        } catch (error) {
            this.showError('Failed to load conversation');
        }
    }

    updateConversationUI() {
        // Update active conversation in sidebar
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // You could add more UI updates here
    }

    // === UI Helper Functions ===
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
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (!document.getElementById('sendButton').disabled) {
                this.sendMessage();
            }
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

    autoResizeTextarea() {
        const textarea = document.getElementById('messageInput');
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }

    setInputState(enabled) {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const fileButton = document.getElementById('fileButton');
        
        messageInput.disabled = !enabled;
        sendButton.disabled = !enabled;
        fileButton.disabled = !enabled;
    }

    // === Modal Functions ===
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

    // === Settings ===
    openSettings() {
        // Load current settings
        const savedPersonality = localStorage.getItem('defaultPersonality') || 'syntaxprime';
        const autoSave = localStorage.getItem('autoSave') !== 'false';
        const showTyping = localStorage.getItem('showTyping') !== 'false';
        
        document.getElementById('defaultPersonality').value = savedPersonality;
        document.getElementById('autoSave').checked = autoSave;
        document.getElementById('showTyping').checked = showTyping;
        
        this.showModal(document.getElementById('settingsModal'));
    }

    saveSettings() {
        const defaultPersonality = document.getElementById('defaultPersonality').value;
        const autoSave = document.getElementById('autoSave').checked;
        const showTyping = document.getElementById('showTyping').checked;
        
        localStorage.setItem('defaultPersonality', defaultPersonality);
        localStorage.setItem('autoSave', autoSave);
        localStorage.setItem('showTyping', showTyping);
        
        this.hideModal(document.getElementById('settingsModal'));
        this.showSuccess('Settings saved!');
    }

    // === UI Actions ===
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        
        // On mobile, use different class
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
        
        // Clear bookmarks
        document.getElementById('bookmarksList').innerHTML = `
            <div class="no-bookmarks">
                <p>No bookmarks yet</p>
                <small>Use "Remember This" to create your first bookmark</small>
            </div>
        `;
        document.getElementById('bookmarkCount').textContent = '0';
        
        // Focus input
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

    logout() {
        // Call the logout API
        fetch('/auth/logout', {
            method: 'POST',
            credentials: 'include'
        }).finally(() => {
            // Clear client-side storage regardless of API response
            sessionStorage.clear();
            localStorage.clear();
            
            // Redirect to login
            window.location.href = '/';
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
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'error' ? 'var(--error)' : type === 'success' ? 'var(--success)' : 'var(--accent-primary)'};
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10001;
            animation: slideInRight 0.3s ease;
        `;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
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
