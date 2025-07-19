






document.addEventListener('DOMContentLoaded', function() {
    const imageFileInput = document.getElementById('image_file');
    const videoFileInput = document.getElementById('video_file');
    const uploadedImageUrlInput = document.getElementById('uploaded_image_url');
    const uploadedVideoUrlInput = document.getElementById('uploaded_video_url');
    const imagePreview = document.getElementById('image_preview');
    const videoPreview = document.getElementById('video_preview');

    // Initial placeholders
    imagePreview.innerHTML = '<span class="preview-placeholder">No image selected</span>';
    videoPreview.innerHTML = '<span class="preview-placeholder">No video selected</span>';

    function uploadFile(file, type, previewElement, urlInput) {
        if (!file) {
            previewElement.innerHTML = `<span class="preview-placeholder">No ${type} selected</span>`;
            urlInput.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        // Show loading indicator
        previewElement.innerHTML = `<span class="preview-placeholder">Uploading ${type}...</span>`;
        urlInput.value = ''; // Clear previous URL

        fetch('/upload_media', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                urlInput.value = data.url; // Store the full URL
                
                // Display thumbnail/preview
                if (data.file_type === 'image') {
                    previewElement.innerHTML = `<img src="${data.thumbnail_url || data.url}" alt="Image Preview" style="max-width:100%; max-height:120px; border-radius: 0.5rem;">`;
                } else if (data.file_type === 'video') {
                    // For video, display the generated thumbnail
                    previewElement.innerHTML = `
                        <div style="position: relative; width: 100%; padding-bottom: 56.25%; height: 0; overflow: hidden; border-radius: 0.5rem;">
                            <img src="${data.thumbnail_url}" alt="Video Thumbnail" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover;">
                            <i class="fas fa-play-circle" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 3rem; color: rgba(255,255,255,0.8); cursor: pointer;"></i>
                        </div>
                    `;
                    // Note: Actual video playback will happen on the task display page, not here.
                }
                // Optional: Flash a success message
                // flashMessage('File uploaded successfully!', 'success');
            } else {
                previewElement.innerHTML = `<span class="preview-placeholder text-danger">Upload failed: ${data.error}</span>`;
                urlInput.value = '';
                // flashMessage(`File upload failed: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            console.error('Upload error:', error);
            previewElement.innerHTML = `<span class="preview-placeholder text-danger">Network error during upload.</span>`;
            urlInput.value = '';
            // flashMessage('Network error during file upload.', 'danger');
        });
    }

    imageFileInput.addEventListener('change', function() {
        uploadFile(this.files[0], 'image', imagePreview, uploadedImageUrlInput);
    });

    videoFileInput.addEventListener('change', function() {
        uploadFile(this.files[0], 'video', videoPreview, uploadedVideoUrlInput);
    });

    // Function to display flash messages (optional, if you want client-side flashes)
    function flashMessage(message, category) {
        const flashContainer = document.querySelector('.flash-messages-container');
        if (flashContainer) {
            const newFlash = document.createElement('div');
            newFlash.classList.add('flash-message', category);
            newFlash.textContent = message;
            flashContainer.appendChild(newFlash);
            setTimeout(() => newFlash.remove(), 5000);
        } else {
            console.log(`Flash (${category}): ${message}`);
        }
    }
});
