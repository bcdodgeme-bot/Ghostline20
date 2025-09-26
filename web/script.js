//=============================================================================
// Syntax Prime V2 - Chat Interface JavaScript
// Handles chat, file uploads, bookmarks, and personality switching
// UPDATED: 9/26/25 - Added minimal anti-duplication fixes
//=============================================================================

// web/script.js - FIXED VERSION
// Enhanced anti-duplication and datetime context

class SyntaxPrimeChat {
    constructor() {
        this.apiBase = window.location.origin;
        this.currentThreadId = null;
        this.currentPersonality = 'syntaxprime';
        this.uploadedFiles = [];
        this.isTyping = false;
        this.bookmarkToCreate = null;
        
        // FIXED: Enhanced anti-duplication protection
        this.isSubmitting = false;
        this.lastSubmitTime = 0;
        this.lastMessage = '';
        this.submitCooldown = 1000; // 1 second minimum between submissions
        this.messageDuplicationWindow = 5000; // 5 seconds to prevent same message

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
        
        // FIXED: Debug datetime context on load
        this.debugDatetimeContext();
    }

    // FIXED: Debug current datetime context
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

        // Chat input
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');

        messageInput.addEventListener('input', this.handleInputChange.bind(this));
        messageInput.addEventListener('keydown', this.handleKeyPress.bind(this));
        sendButton.addEventListener('click', this.sendMessage.bind(this));

        // File upload
        document.getElementById('fileUpload').addEventListener('change', this.handleFileUpload.bind(this));

        // Bookmarks
        document.getElementById('bookmarkBtn').addEventListener('click', this.openBookmarkModal.bind(this));
    }

    // FIXED: Enhanced message sending with strict anti-duplication
    async sendMessage() {
        console.log('🚀 sendMessage called');
        
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();

        // FIXED: Enhanced validation
        if (!message && this.uploadedFiles.length === 0) {
            console.log('❌ Empty message, not sending');
            return;
        }

        // FIXED: Strict anti-duplication checks
        const now = Date.now();
        
        // Check if already submitting
        if (this.isSubmitting) {
            console.log('❌ Already submitting, blocking duplicate');
            return;
        }
        
        // Check cooldown period
        if (now - this.lastSubmitTime < this.submitCooldown) {
            console.log('❌ Within cooldown period, blocking rapid submission');
            return;
        }
        
        // Check for duplicate message content
        if (message === this.lastMessage && now - this.lastSubmitTime < this.messageDuplicationWindow) {
            console.log('❌ Duplicate message within window, blocking');
            return;
        }

        // FIXED: Set submission state immediately
        this.isSubmitting = true;
        this.lastSubmitTime = now;
        this.lastMessage = message;

        console.log('✅ Sending message:', message);

        // Disable input immediately
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

            // FIXED: Enhanced datetime context with explicit timezone
            const currentDateTime = new Date();
            const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            
            const requestData = {
                message: message,
                personality_id: this.currentPersonality,
                thread_id: this.currentThreadId,
                include_knowledge: true,
                // FIXED: Comprehensive datetime context
                datetime_context: {
                    current_date: currentDateTime.toISOString().split('T')[0],
                    current_time_24h: currentDateTime.toLocaleTimeString('en-US', {
                        hour12: false,
                        hour: '2-digit',
                        minute: '2-digit'
                    }),
                    current_time_12h: currentDateTime.toLocaleTimeString('en-US', {
                        hour12: true
                    }),
                    day_of_week: currentDateTime.toLocaleDateString('en-US', { weekday: 'long' }),
                    month_name: currentDateTime.toLocaleDateString('en-US', { month: 'long' }),
                    full_datetime: currentDateTime.toLocaleDateString('en-US', {
                        weekday: 'long',
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    }),
                    timezone: timeZone,
                    iso_timestamp: currentDateTime.toISOString(),
                    unix_timestamp: Math.floor(currentDateTime.getTime() / 1000)
                },
                // FIXED: Anti-duplication metadata
                client_metadata: {
                    submission_timestamp: now,
                    client_message_id: `client_${now}_${Math.random().toString(36).substr(2, 9)}`,
                    anti_duplication: true
                }
            };

            console.log('📤 Sending request with datetime context:', requestData.datetime_context);

            // Send message
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
                knowledgeSources: response.knowledge_sources || [],
                datetimeUsed: response.datetime_context_used || 'Unknown'
            });

            // Show remember button
            this.showRememberButton(response.message_id);

        } catch (error) {
            console.error('❌ Chat error:', error);
            this.hideTypingIndicator();
            this.addMessage('assistant', `Sorry, I encountered an error: ${error.message || 'Please try again.'}`);
        } finally {
            // FIXED: Always reset submission state
            this.isSubmitting = false;
            this.setInputState(true);
            
            // Re-focus input
            setTimeout(() => {
                document.getElementById('messageInput').focus();
            }, 100);
        }
    }

    // FIXED: Enhanced input handling with duplication prevention
    handleInputChange() {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        
        // Update character count
        this.updateCharCount();
        
        // FIXED: Enhanced send button state management
        const hasContent = messageInput.value.trim().length > 0 || this.uploadedFiles.length > 0;
        const canSend = hasContent && !this.isTyping && !this.isSubmitting;
        
        sendButton.disabled = !canSend;
        
        // Auto-resize textarea
        this.autoResizeTextarea();
    }

    // FIXED: Enhanced key press handling
    handleKeyPress(event) {
        // FIXED: Prevent submission if already submitting
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            
            // Only submit if not already submitting and button is enabled
            const sendButton = document.getElementById('sendButton');
            if (!sendButton.disabled && !this.isSubmitting) {
                this.sendMessage();
            }
        }
    }

    // FIXED: Enhanced input state management
    setInputState(enabled) {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const fileUpload = document.getElementById('fileUpload');

        messageInput.disabled = !enabled;
        sendButton.disabled = !enabled || this.isSubmitting;
        fileUpload.disabled = !enabled;

        // Visual feedback
        if (enabled) {
            messageInput.style.opacity = '1';
            sendButton.style.opacity = '1';
        } else {
            messageInput.style.opacity = '0.6';
            sendButton.style.opacity = '0.6';
        }
    }

    // FIXED: Enhanced message display with debugging info
    addMessage(role, content, metadata = {}) {
        const messagesContainer = document.querySelector('.chat-messages');
        const messageElement = document.createElement('div');
        messageElement.className = `message ${role}`;

        // Create avatar
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? '👤' : '🤖';

        // Create content container
        const contentContainer = document.createElement('div');
        contentContainer.className = 'message-content';

        // Create message bubble
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        // Create message text
        const text = document.createElement('div');
        text.className = 'message-text';
        text.innerHTML = this.formatMessageContent(content);

        bubble.appendChild(text);
        contentContainer.appendChild(bubble);

        // FIXED: Add debugging info for assistant messages
        if (role === 'assistant' && metadata.datetimeUsed) {
            const debugInfo = document.createElement('div');
            debugInfo.className = 'message-debug';
            debugInfo.style.fontSize = '0.7rem';
            debugInfo.style.color = 'var(--text-tertiary)';
            debugInfo.style.marginTop = 'var(--spacing-xs)';
            debugInfo.textContent = `Datetime context: ${metadata.datetimeUsed}`;
            contentContainer.appendChild(debugInfo);
        }

        // Add message actions for assistant messages
        if (role === 'assistant') {
            const actions = this.createMessageActions(metadata.messageId);
            contentContainer.appendChild(actions);
        }

        // Add timestamp
        const timestamp = document.createElement('div');
        timestamp.className = 'message-meta';
        timestamp.textContent = new Date().toLocaleTimeString();
        contentContainer.appendChild(timestamp);

        // Assemble message
        messageElement.appendChild(avatar);
        messageElement.appendChild(contentContainer);

        // Add to chat
        messagesContainer.appendChild(messageElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Animate in
        messageElement.style.opacity = '0';
        messageElement.style.transform = 'translateY(20px)';
        
        requestAnimationFrame(() => {
            messageElement.style.transition = 'all 0.3s ease';
            messageElement.style.opacity = '1';
            messageElement.style.transform = 'translateY(0)';
        });
    }

    // Rest of the methods remain the same...
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
        const charCount = document.querySelector('.char-count');
        
        if (charCount) {
            const count = messageInput.value.length;
            charCount.textContent = `${count}/4000`;
            
            if (count > 3500) {
                charCount.style.color = 'var(--error)';
            } else if (count > 3000) {
                charCount.style.color = 'var(--warning)';
            } else {
                charCount.style.color = 'var(--text-tertiary)';
            }
        }
    }

    // FIXED: Enhanced API call with better error handling
    async apiCall(endpoint, method = 'GET', data = null) {
        const url = `${this.apiBase}${endpoint}`;
        console.log(`🌐 API Call: ${method} ${url}`, data ? data : '');
        
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const result = await response.json();
            console.log(`✅ API Response:`, result);
            return result;
            
        } catch (error) {
            console.error(`❌ API Error:`, error);
            throw error;
        }
    }

    // Initialize the chat system
    showTypingIndicator() {
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
        
        const messagesContainer = document.querySelector('.chat-messages');
        messagesContainer.appendChild(indicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    hideTypingIndicator() {
        const indicator = document.querySelector('.typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    // Placeholder methods for other functionality
    toggleSidebar() { console.log('Toggle sidebar'); }
    startNewChat() {
        this.currentThreadId = null;
        document.querySelector('.chat-messages').innerHTML = '';
        console.log('New chat started');
    }
    openSettings() { console.log('Open settings'); }
    logout() { window.location.href = '/'; }
    loadPersonalities() { console.log('Load personalities'); }
    loadConversations() { console.log('Load conversations'); }
    setupDragAndDrop() { console.log('Setup drag and drop'); }
    handleFileUpload() { console.log('Handle file upload'); }
    clearUploadedFiles() { this.uploadedFiles = []; }
    openBookmarkModal() { console.log('Open bookmark modal'); }
    createMessageActions(messageId) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        return actions;
    }
    showRememberButton(messageId) { console.log('Show remember button for', messageId); }
}

// FIXED: Enhanced initialization with error handling
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 FIXED: Initializing SyntaxPrime Chat...');
    
    try {
        window.syntaxPrimeChat = new SyntaxPrimeChat();
        console.log('✅ FIXED: SyntaxPrime Chat initialized successfully');
    } catch (error) {
        console.error('❌ FIXED: Failed to initialize chat:', error);
    }
});
