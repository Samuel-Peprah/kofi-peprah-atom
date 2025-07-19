// static/js/main.js

document.addEventListener('DOMContentLoaded', function() {
    // --- Mobile Navigation Toggler ---
    const navbarToggler = document.getElementById('navbarToggler');
    const navbarCollapse = document.getElementById('navbarCollapse');

    if (navbarToggler && navbarCollapse) {
        navbarToggler.addEventListener('click', function() {
            navbarCollapse.classList.toggle('show');
        });
    }

    // --- Flash Message Auto-Hide ---
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 500); // Remove after fade out
        }, 5000); // Hide after 5 seconds
    });

    // --- Dynamic Form Section Toggler (for Outpatient/Home Health forms) ---
    // This will be implemented more fully when we build the forms.
    // Example: If you have sections that should expand/collapse
    const collapsibleHeaders = document.querySelectorAll('.collapsible-header');
    collapsibleHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const content = this.nextElementSibling; // The content div after the header
            if (content && content.classList.contains('collapsible-content')) {
                content.style.display = content.style.display === 'block' ? 'none' : 'block';
                this.querySelector('.toggle-icon').classList.toggle('fa-chevron-down');
                this.querySelector('.toggle-icon').classList.toggle('fa-chevron-up');
            }
        });
    });

    // --- Add more global JS functionality here as needed ---
});
