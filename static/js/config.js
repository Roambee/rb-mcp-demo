// Toggle password visibility
function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    const toggle = field.nextElementSibling;
    const icon = toggle.querySelector('img');

    if (field.type === 'password') {
        field.type = 'text';
        icon.src = '../static/images/view--off.svg';
    } else {
        field.type = 'password';
        icon.src = '../static/images/view-icon.svg';
    }

}

// Clear form
function clearForm() {
    document.getElementById('openai_key').value = '';
    document.getElementById('roambee_key').value = '';
    hideError();
    
    // Reset password field types
    document.getElementById('openai_key').type = 'password';
    document.getElementById('roambee_key').type = 'password';
    
    // Reset eye icons
    document.querySelectorAll('.toggle-password img').forEach(icon => {
        icon.src = '../static/images/view-icon.svg';
    });
}

// Show error message
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    const errorText = document.getElementById('errorText');
    errorText.textContent = message;
    errorDiv.style.display = 'flex';
}

// Hide error message
function hideError() {
    document.getElementById('errorMessage').style.display = 'none';
}

// Show loading state
function showLoading() {
    document.getElementById('configForm').style.display = 'none';
    document.getElementById('loading').style.display = 'block';
    hideError();
}

// Hide loading state
function hideLoading() {
    document.getElementById('configForm').style.display = 'flex';
    document.getElementById('loading').style.display = 'none';
}

// Handle form submission
document.getElementById('configForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const openaiKey = document.getElementById('openai_key').value.trim();
    const roambeeKey = document.getElementById('roambee_key').value.trim();
    
    // Basic validation
    if (!openaiKey || !roambeeKey) {
        showError('Please fill in both API keys');
        return;
    }
    
    if (!openaiKey.startsWith('sk-')) {
        showError('OpenAI API key should start with "sk-"');
        return;
    }
    
    if (openaiKey.length < 20) {
        showError('OpenAI API key seems too short');
        return;
    }
    
    if (roambeeKey.length < 10) {
        showError('Roambee API key seems too short');
        return;
    }
    
    // Show loading state
    showLoading();
    
    try {
        const formData = new FormData();
        formData.append('openai_key', openaiKey);
        formData.append('roambee_key', roambeeKey);
        
        const response = await fetch('/validate-keys', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Redirect to chat page
            window.location.href = result.redirect;
        } else {
            hideLoading();
            showError(result.message || 'Invalid API keys. Please check and try again.');
        }
    } catch (error) {
        hideLoading();
        showError('Failed to validate API keys. Please check your connection and try again.');
        console.error('Validation error:', error);
    }
});

// Add some visual feedback for input fields
document.querySelectorAll('input').forEach(input => {
    input.addEventListener('input', function() {
        hideError();
    });
    
    input.addEventListener('paste', function() {
        setTimeout(() => {
            hideError();
        }, 100);
    });
});

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + Enter to submit
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        document.getElementById('configForm').dispatchEvent(new Event('submit'));
    }
    
    // Escape to clear form
    if (e.key === 'Escape') {
        clearForm();
    }
}); 