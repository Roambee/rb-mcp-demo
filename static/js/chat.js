// Global state
let chatHistory = [];
let currentTheme = localStorage.getItem('theme') || 'light';
let isLoading = false;

// Initialize the chat application
document.addEventListener('DOMContentLoaded', function() {
    initializeTheme();
    loadChatHistory();
    setupEventListeners();
    autoResizeTextarea();
});

// Theme management
function initializeTheme() {
    document.body.setAttribute('data-theme', currentTheme);
    updateThemeIcon();
    updateThemeButtons();
    updateHeaderLogo();
}

function toggleTheme() {
    currentTheme = currentTheme === 'light' ? 'dark' : 'light';
    setTheme(currentTheme);
}

function setTheme(theme) {
    currentTheme = theme;
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    updateThemeIcon();
    updateThemeButtons();
    updateHeaderLogo();
}

function updateHeaderLogo() {
    const logo = document.getElementById('roambeeLogo');
    if (!logo) return;

    if (currentTheme === 'dark') {
        logo.src = '../static/images/roambee-logo-blackbg.svg';
    } else {
        logo.src = '../static/images/roambee-logo-whitebg.svg';
    }
}

function updateThemeIcon() {
    const themeIcon = document.getElementById('themeIcon');
    themeIcon.src = currentTheme === 'light' ? "../static/images/moon.svg" : "../static/images/sun.svg"; 
}

function updateThemeButtons() {
    const buttons = document.querySelectorAll('.theme-btn');
    buttons.forEach(btn => btn.classList.remove('active'));

    if (currentTheme === 'light') {
        document.querySelector(".theme-btn[onclick*='light']").classList.add('active');
    } else{
        document.querySelector(".theme-btn[onclick*='dark']").classList.add('active');
    }
}

// Settings modal
function showSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.add('show');
}

function hideSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.remove('show');
}

function goToConfig() {
    if (confirm('Are you sure you want to reconfigure your API keys? This will clear your current session.')) {
        fetch('/reset-config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                window.location.href = data.redirect || '/';
            }
        })
        .catch(error => {
            console.error('Error resetting config:', error);
            alert('Failed to reset configuration. Please try again.');
        });
    }
}

// Sidebar management
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

function startNewChat() {
    if (chatHistory.length > 0) {
        if (confirm('Start a new chat? Current conversation will be saved to history.')) {
            clearCurrentChat();
        }
    } else {
        clearCurrentChat();
    }
}

function clearCurrentChat() {
    chatHistory = [];
    const chatContainer = document.getElementById('chatContainer');
    chatContainer.style.justifyContent = 'center';
    chatContainer.style.alignContent = 'center';
    chatContainer.innerHTML = `
        <div class="welcome-message">
            <img src="../static/images/roambee-logo-bee.svg" alt="Icon" width="auto" height="60px"/>
            <h2>Welcome to Roambee MCP Demo</h2>
        </div>
    `;

    const feedbackMessage = document.getElementById('feedbackMessage');
    if (feedbackMessage) {
        feedbackMessage.remove();
    }
    // Add new chat to history sidebar
    addChatToHistory('New Chat', new Date());
}

function selectChat(element) {
    // Remove active class from all history items
    document.querySelectorAll('.history-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add active class to selected item
    element.classList.add('active');
}

function addChatToHistory(title, date) {
    const chatHistoryContainer = document.getElementById('chatHistory');
    
    const historyItem = document.createElement('div');
    historyItem.className = 'history-item active';
    historyItem.onclick = () => selectChat(historyItem);
    
    historyItem.innerHTML = `
        <div class="history-content">
            <img src="../static/images/chat.svg" alt="Message Icon" class="icon" width="20px" height="auto"/>
            <span>${title}</span>
        </div>
    `;
    
    // Remove active class from other items
    document.querySelectorAll('.history-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add new item at the top
    chatHistoryContainer.insertBefore(historyItem, chatHistoryContainer.firstChild);
}

// Message handling
function setupEventListeners() {
    const messageForm = document.getElementById('messageForm');
    const messageInput = document.getElementById('messageInput');
    
    // Form submission
    messageForm.addEventListener('submit', handleMessageSubmit);
    
    // Textarea auto-resize and character count
    messageInput.addEventListener('input', function() {
        autoResizeTextarea();
        updateCharCount();
    });
    
    // Enter key handling (Shift+Enter for new line, Enter to send)
    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!isLoading && this.value.trim()) {
                messageForm.dispatchEvent(new Event('submit'));
            }
        }
    });
    
    // Close modal when clicking outside
    document.getElementById('settingsModal').addEventListener('click', function(e) {
        if (e.target === this) {
            hideSettings();
        }
    });
    
    // ESC key to close modal
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideSettings();
        }
    });
}

function autoResizeTextarea() {
    const textarea = document.getElementById('messageInput');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

function updateCharCount() {
    const textarea = document.getElementById('messageInput');
    const charCount = document.querySelector('.char-count');
    const length = textarea.value.length;
    charCount.textContent = `${length} / 4000`;
    
    if (length > 3800) {
        charCount.style.color = '#e53e3e';
    } else if (length > 3500) {
        charCount.style.color = '#d69e2e';
    } else {
        charCount.style.color = 'var(--text-primary)';
    }
}

async function handleMessageSubmit(e) {
    e.preventDefault();
    
    if (isLoading) return;
    
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message) return;
    
    // Add user message to chat
    addMessageToChat('user', message);
    
    // Clear input
    messageInput.value = '';
    autoResizeTextarea();
    updateCharCount();
    
    // Show loading state
    showLoading();
    
    try {
        const formData = new FormData();
        formData.append('message', message);
        
        const response = await fetch('/send-message', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Failed to send message');
        }
        
        const data = await response.json();
        
        // Add AI response to chat
        addMessageToChat('assistant', data.response);
        
        // Update chat history
        chatHistory = data.chat_history || [];
        
        // Update chat title in sidebar if this is the first message
        if (chatHistory.length === 2) { // User + Assistant message
            updateChatTitle(message);
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        addMessageToChat('assistant', "Sorry, I encountered an error. Please try again.");
    } finally {
        hideLoading();
    }
}

function addMessageToChat(role, content) {
    const chatContainer = document.getElementById('chatContainer');
    
    // Remove welcome message if it exists
    const welcomeMessage = chatContainer.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
        chatContainer.style.alignContent = 'flex-start';
        chatContainer.style.flexWrap = 'wrap';
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    // Render content based on role
    if (role === 'assistant' && typeof marked !== 'undefined') {
        // Configure marked for security
        marked.setOptions({
            breaks: true,
            gfm: true,
            sanitize: false, // We'll handle sanitization
            smartLists: true,
            smartypants: true
        });
        
        // Basic sanitization - remove dangerous tags
        let sanitizedContent = content
            .replace(/<script[^>]*>.*?<\/script>/gi, '')
            .replace(/<iframe[^>]*>.*?<\/iframe>/gi, '')
            .replace(/<object[^>]*>.*?<\/object>/gi, '')
            .replace(/<embed[^>]*>/gi, '')
            .replace(/javascript:/gi, '');
        
        // Render Markdown to HTML
        messageContent.innerHTML = marked.parse(sanitizedContent);
        
        // Make links open in new tab
        const links = messageContent.querySelectorAll('a');
        links.forEach(link => {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        });
    } else {
        // For user messages or if marked is not available, use plain text
        messageContent.textContent = content;
    }
    
    if (role === 'user') {
        messageDiv.appendChild(messageContent);
        // messageDiv.appendChild(avatar);
    } else {
        // messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
    }

    if (role === 'assistant') {
        const feedbackMessage = createFeedbackMessage();
        messageDiv.appendChild(feedbackMessage);
    }
    
    chatContainer.appendChild(messageDiv);
    
    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function createFeedbackMessage() {
    const feedbackDiv = document.createElement('div');
    feedbackDiv.className = 'message feedback-message'; // use your CSS for .message and add .feedback-message for any extra styling

    const thumbsUpBtn = document.createElement('button');
    thumbsUpBtn.className = 'feedback-btn thumbs-up'; // add your CSS classes for buttons
    thumbsUpBtn.title = 'Thumbs Up';
    thumbsUpBtn.innerHTML = '<img src="../static/images/thumbs-up.svg" class="thumb" alt="Thumbs Up" width="24" height="24">';

    const thumbsDownBtn = document.createElement('button');
    thumbsDownBtn.className = 'feedback-btn thumbs-down';
    thumbsDownBtn.title = 'Thumbs Down';
    thumbsDownBtn.innerHTML = '<img src="../static/images/thumbs-down.svg" alt="Thumbs Down" width="24" height="24">';

    const handleFeedbackClick = async (e, feedbackType) => {
        
        const clickedBtn = e.currentTarget; // Ensures we get the button, even if an <img> was clicked
        const otherBtn = clickedBtn === thumbsUpBtn ? thumbsDownBtn : thumbsUpBtn;

        console.log(clickedBtn,otherBtn);

        const img = clickedBtn.querySelector('img');
        if (img) {
            if (feedbackType === 'Thumbs Up') {
                img.src = '../static/images/thumbs-up--filled.svg'; // active/selected thumbs up image
            } else if (feedbackType === 'Thumbs Down') {
                img.src = '../static/images/thumbs-down--filled.svg'; // active/selected thumbs down image
            }
        }

        // Disable clicked button
        clickedBtn.disabled = true;

        // Remove the other button
        if (otherBtn.parentNode) {
            otherBtn.parentNode.removeChild(otherBtn);
        }

        const messageDiv = e.target.closest('.message.assistant');
        if (!messageDiv) return;

        const messageContentDiv = messageDiv.querySelector('.message-content');
        if (!messageContentDiv) return;

        const messageText = messageContentDiv.textContent || '';
        const formData = new FormData();

        formData.append('feedback', feedbackType);
        formData.append('message', messageText);

        try {
            const res = await fetch('/send-feedback', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            console.log('Feedback sent:', data);
        } catch (error) {
            console.error('Error sending feedback:', error);
        }
    };

    thumbsUpBtn.addEventListener('click', (e) => handleFeedbackClick(e, "Thumbs Up"));
    thumbsDownBtn.addEventListener('click', (e) => handleFeedbackClick(e, "Thumbs Down"));

  feedbackDiv.appendChild(thumbsUpBtn);
  feedbackDiv.appendChild(thumbsDownBtn);

  return feedbackDiv;
}
function updateChatTitle(firstMessage) {
    const activeHistoryItem = document.querySelector('.history-item.active');
    if (activeHistoryItem) {
        const titleSpan = activeHistoryItem.querySelector('.history-content span');
        const shortTitle = firstMessage.length > 30 ? firstMessage.substring(0, 30) + '...' : firstMessage;
        titleSpan.textContent = shortTitle;
    }
}

function showLoading() {
    isLoading = true;
    const sendBtn = document.getElementById('sendBtn');
    const loadingOverlay = document.getElementById('loadingOverlay');
    
    sendBtn.disabled = true;
    loadingOverlay.classList.add('show');
}

function hideLoading() {
    isLoading = false;
    const sendBtn = document.getElementById('sendBtn');
    const loadingOverlay = document.getElementById('loadingOverlay');
    
    sendBtn.disabled = false;
    loadingOverlay.classList.remove('show');
}

// Load chat history from server
async function loadChatHistory() {
    try {
        const response = await fetch('/chat-history');
        if (response.ok) {
            const data = await response.json();
            chatHistory = data.chat_history || [];
            
            // Render existing chat history
            if (chatHistory.length > 0) {
                const chatContainer = document.getElementById('chatContainer');
                const welcomeMessage = chatContainer.querySelector('.welcome-message');
                if (welcomeMessage) {
                    welcomeMessage.remove();
                     chatContainer.style.alignContent = 'flex-start';
                    chatContainer.style.flexWrap = 'wrap';
                }
                
                chatHistory.forEach(msg => {
                    addMessageToChat(msg.role, msg.content);
                });
            }
        }
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

// Utility functions
function truncateText(text, maxLength) {
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

// Handle window resize for responsive design
window.addEventListener('resize', function() {
    if (window.innerWidth > 768) {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.remove('open');
    }
});

// Handle clicks outside sidebar on mobile
document.addEventListener('click', function(e) {
    const sidebar = document.getElementById('sidebar');
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    
    if (window.innerWidth <= 768 && 
        sidebar.classList.contains('open') && 
        !sidebar.contains(e.target) && 
        !mobileMenuBtn.contains(e.target)) {
        sidebar.classList.remove('open');
    }
}); 

// document.getElementById('modal-close-btn').addEventListener('click', () => {
//     const modal = document.getElementById('feedbackModal');
//     modal.classList.remove('show');
// });

// document.getElementById('submitFeedbackBtn').addEventListener('click', () => {
//     const subject = document.getElementById('feedbackSubject').value.trim();
//     const text = document.getElementById('feedbackText').value.trim();

//     if (!subject || !text) {
//         alert('Please fill in both subject and feedback.');
//         return;
//     }

//     const formData = new FormData();
//     formData.append('feedback', subject); 
//     formData.append('message', text);

//     fetch('/send-feedback', {
//         method: 'POST',
//         body: formData
//     })
//     .then(res => res.json())
//     .then(data => {
//         console.log('Feedback sent:', data);
//     })
//     .catch(console.error);

//     const modal = document.getElementById('feedbackModal');
//     modal.classList.remove('show');
// });