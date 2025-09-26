//=============================================================================
// Syntax Prime V2 - Chat Interface JavaScript
// Handles chat, file uploads, bookmarks, and personality switching
// UPDATED: 9/26/25 - Added minimal anti-duplication fixes
//=============================================================================

class SyntaxPrimeChat {
    constructor() {
        this.apiBase = window.location.origin; // Assumes API is on same domain
        this.currentThreadId = null;
        this.currentPersonality = 'syntaxprime';
        this.uploadedFiles = [];
        this.isTyping = false;
        this.bookmarkToCreate = null;
        // NEW: Anti-duplication protection
        this.isSubmitting = false;
        this.lastSubmitTime = 0;

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

        // UPDATED: Add anti-duplication protection
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

    // NEW: Anti-duplication send handler
    handleSendClick(event) {
        event.preventDefault();
        event.stopPropagation();
        
        const now = Date.now();
        if (this.isSubmitting || (now - this.lastSubmitTime) < 1000) {
            console.log('🛡️ Double submission prevented');
            return;
        }
        
        this.sendMessage();
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
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${sessionStorage.getItem('syntaxprime_password')}` // Simple auth
                }
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

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            this.showError(`Request failed: ${error.message}`);
            throw error;
        }
    }

    // === Chat Functions ===
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

        // Disable input
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

            // Prepare request data with datetime context
            const currentDateTime = new Date();
            const requestData = {
                message: message,
                personality_id: this.currentPersonality,
                thread_id: this.currentThreadId,
                include_knowledge: true,
                // NEW: Provide current date/time context for Syntax
                context: {
                    current_date: currentDateTime.toISOString().split('T')[0],
                    current_time: currentDateTime.toLocaleTimeString('en-US', { hour12: false }),
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timestamp: currentDateTime.toISOString()
                }
            };

            // Send message
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

            // Copy button
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

            // Remember button
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

            // Feedback buttons
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

    async submitFeedback(messageId, feedbackType) {
        try {
            // Visual feedback first
            const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
            if (messageDiv) {
                const feedbackBtn = messageDiv.querySelector(`.feedback-${feedbackType}`);
                if (feedbackBtn) {
                    feedbackBtn.style.background = 'var(--accent-primary)';
                    feedbackBtn.style.color = 'white';
                    feedbackBtn.style.transform = 'scale(0.9)';
                    setTimeout(() => {
                        feedbackBtn.style.background = '';
                        feedbackBtn.style.color = '';
                        feedbackBtn.style.transform = '';
                    }, 1000);
                }
            }

            // Submit feedback to backend
            const response = await this.apiCall('/ai/feedback', 'POST', {
                message_id: messageId,
                feedback_type: feedbackType,
                feedback_text: null
            });

            this.showSuccess(response.message || 'Feedback submitted successfully');

        } catch (error) {
            console.error('Feedback submission failed:', error);
            this.showError('Failed to submit feedback. Please try again.');
        }
    }

    formatMessageContent(content) {
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    // === Input Handling ===
    handleInputChange() {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');

        this.updateCharCount();

        const hasContent = messageInput.value.trim().length > 0 || this.uploadedFiles.length > 0;
        sendButton.disabled = !hasContent || this.isTyping || this.isSubmitting;

        this.autoResizeTextarea();
    }

    handleKeyPress(event) {
        // UPDATED: Add anti-duplication protection
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

    autoResizeTextarea() {
        const textarea = document.getElementById('messageInput');
        textarea.style.height = 'auto';
        const newHeight = Math.min(textarea.scrollHeight, 150);
        textarea.style.height = newHeight + 'px';

        const inputContainer = document.querySelector('.chat-input-container');
        const chatMessages = document.querySelector('.chat-messages');

        if (inputContainer && chatMessages) {
            const inputHeight = inputContainer.offsetHeight;
            chatMessages.style.paddingBottom = `${inputHeight + 20}px`;
        }
    }

    updateCharCount() {
        const messageInput = document.getElementById('messageInput');
        const charCount = document.getElementById('charCount');
        const currentLength = messageInput.value.length;
        const maxLength = 8000;

        if (charCount) {
            charCount.textContent = `${currentLength}/${maxLength}`;

            if (currentLength > maxLength * 0.8) {
                charCount.style.color = 'var(--warning)';
            } else {
                charCount.style.color = 'var(--text-tertiary)';
            }
        }
    }

    showTypingIndicator() {
        const messagesContainer = document.getElementById('chatMessages');

        const existing = document.getElementById('typingIndicator');
        if (existing) {
            existing.remove();
        }

        const typingDiv = document.createElement('div');
        typingDiv.id = 'typingIndicator';
        typingDiv.className = 'typing-indicator';
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

    // === File Handling ===
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
            if (uploadArea) uploadArea.style.display = 'block';
            if (filesContainer) {
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
            }
        } else {
            if (uploadArea) uploadArea.style.display = 'none';
        }
    }

    removeFile(index) {
        this.uploadedFiles.splice(index, 1);
        this.updateFileUploadArea();
        this.handleInputChange();
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

    // === UI Controls ===
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
        this.showSuccess('Remember functionality coming soon!');
    }

    // === Modals ===
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

    showBookmarkModal() {
        this.showModal(document.getElementById('bookmarkModal'));
    }

    saveBookmark() {
        this.hideModal(document.getElementById('bookmarkModal'));
        this.showSuccess('Bookmark saved!');
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

    // === Notifications ===
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

    // === Data Loading ===
    async loadPersonalities() {
        try {
            const response = await this.apiCall('/ai/personalities');

            if (response && response.personalities) {
                const select = document.getElementById('personalitySelect');
                select.innerHTML = '';

                response.personalities.forEach(personality => {
                    const option = document.createElement('option');
                    option.value = personality.id;
                    option.textContent = personality.name;
                    if (personality.is_default) {
                        option.selected = true;
                        this.currentPersonality = personality.id;
                    }
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to load personalities:', error);
        }
    }

    async loadConversations() {
        try {
            const response = await this.apiCall('/ai/conversations');

            if (response && response.conversations) {
                const conversationsList = document.querySelector('.conversations-list');
                const loadingElement = conversationsList.querySelector('.loading-conversations');

                if (loadingElement) {
                    loadingElement.remove();
                }

                response.conversations.forEach(conversation => {
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
        } catch (error) {
            console.error('Failed to load conversations:', error);
            const conversationsList = document.querySelector('.conversations-list');
            if (conversationsList) {
                conversationsList.innerHTML = '<div class="error">Failed to load conversations</div>';
            }
        }
    }

    async loadConversation(threadId) {
        try {
            this.currentThreadId = threadId;
            const response = await this.apiCall(`/ai/conversations/${threadId}`);

            if (response && response.messages) {
                const messagesContainer = document.getElementById('chatMessages');
                messagesContainer.innerHTML = '';

                response.messages.forEach(message => {
                    this.addMessage(message.role, message.content, {
                        messageId: message.id,
                        timestamp: message.created_at
                    });
                });
            }
        } catch (error) {
            console.error('Failed to load conversation:', error);
            this.showError('Failed to load conversation');
        }
    }

    setupDragAndDrop() {
        const chatContainer = document.querySelector('.chat-container');
        if (!chatContainer) return;

        let dragCounter = 0;

        chatContainer.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            this.showDragOverlay();
        });

        chatContainer.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter === 0) {
                this.hideDragOverlay();
            }
        });

        chatContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        chatContainer.addEventListener('drop', (e) => {
            e.preventDefault();
            dragCounter = 0;
            this.hideDragOverlay();

            const files = Array.from(e.dataTransfer.files);
            files.forEach(file => this.addUploadedFile(file));
        });
    }

    showDragOverlay() {
        let overlay = document.getElementById('dragOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'dragOverlay';
            overlay.className = 'drag-overlay';
            overlay.innerHTML = `
                <div class="drag-content">
                    <div class="drag-icon">📁</div>
                    <h3>Drop files here</h3>
                    <p>Supports images, PDFs, text files, and CSV</p>
                </div>
            `;
            document.body.appendChild(overlay);
        }
        overlay.style.display = 'flex';
    }

    hideDragOverlay() {
        const overlay = document.getElementById('dragOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
}

// UPDATED: Initialize with DOM ready protection
let syntaxChat = null;

function initializeSyntaxChat() {
    if (syntaxChat) {
        console.log('🛡️ SyntaxChat already initialized, skipping');
        return;
    }

    console.log('🚀 Initializing SyntaxChat');
    syntaxChat = new SyntaxPrimeChat();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSyntaxChat);
} else {
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
