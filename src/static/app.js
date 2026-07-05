document.addEventListener('DOMContentLoaded', () => {
    // --- Session Management ---
    let sessionId = localStorage.getItem('docuflow_session_id');
    if (!sessionId) {
        sessionId = 'sess-' + Math.random().toString(36).substring(2, 10);
        localStorage.setItem('docuflow_session_id', sessionId);
    }
    
    const sessionIdInput = document.getElementById('sessionIdInput');
    const restoreSessionBtn = document.getElementById('restoreSessionBtn');
    
    if (sessionIdInput) {
        sessionIdInput.value = sessionId;
        restoreSessionBtn.addEventListener('click', () => {
            const newSessionId = sessionIdInput.value.trim();
            if (newSessionId && newSessionId !== sessionId) {
                localStorage.setItem('docuflow_session_id', newSessionId);
                // Also update the URL to pass the session ID to the server for the initial render
                window.location.href = `/?session_id=${newSessionId}`;
            }
        });
    }

    // Pass session id on load if not present in URL
    const urlParams = new URLSearchParams(window.location.search);
    if (!urlParams.has('session_id')) {
        window.history.replaceState(null, '', `/?session_id=${sessionId}`);
        // We don't reload here, we just rely on the next refresh or the user clicking restore.
        // Actually, to make it work immediately on first visit, we should reload once if the server didn't get it.
        // But for now, we'll let the user refresh or rely on AJAX calls.
        // Wait, better yet: if the URL doesn't have the session_id, redirect immediately to load the correct list.
        window.location.href = `/?session_id=${sessionId}`;
    }

    // --- Sidebar Toggle ---
    const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
    const toggleSidebarBtnHidden = document.getElementById('toggleSidebarBtnHidden');
    const dashboardGrid = document.querySelector('.dashboard-grid');
    
    function toggleSidebar() {
        dashboardGrid.classList.toggle('sidebar-collapsed');
        if (dashboardGrid.classList.contains('sidebar-collapsed')) {
            if (toggleSidebarBtnHidden) toggleSidebarBtnHidden.style.display = 'block';
        } else {
            if (toggleSidebarBtnHidden) toggleSidebarBtnHidden.style.display = 'none';
        }
    }
    
    if (toggleSidebarBtn) toggleSidebarBtn.addEventListener('click', toggleSidebar);
    if (toggleSidebarBtnHidden) toggleSidebarBtnHidden.addEventListener('click', toggleSidebar);

    // --- Update Document Count ---
    function updateDocCount() {
        const rows = document.querySelectorAll('tbody tr:not(.empty-state)');
        const countBox = document.getElementById('docCountBox');
        if (countBox) {
            countBox.style.display = 'inline-block';
            countBox.querySelector('span').textContent = rows.length;
        }
        
        // Also add file icons to cells
        rows.forEach(row => {
            const cell = row.querySelector('.filename-cell');
            if (cell && !cell.querySelector('.file-icon')) {
                const cellText = cell.getAttribute('title') || cell.textContent;
                // Avoid duplicating if icon is already there
                if (!cellText.includes('📄') && !cellText.includes('📕') && !cellText.includes('📘') && !cellText.includes('📗') && !cellText.includes('🖼️')) {
                    const filename = cellText;
                    const ext = filename.split('.').pop().toLowerCase();
                    let icon = '📄';
                    if (ext === 'pdf') icon = '📕';
                    else if (ext === 'docx' || ext === 'doc') icon = '📘';
                    else if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') icon = '📗';
                    else if (ext === 'png' || ext === 'jpg' || ext === 'jpeg') icon = '🖼️';
                    
                    cell.innerHTML = `<span class="file-icon">${icon}</span> <span>${filename}</span>`;
                }
            }
        });
    }
    
    updateDocCount();

    // --- File Upload ---
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadForm = document.getElementById('uploadForm');
    const statusMsg = document.getElementById('uploadStatus');
    const fileMsg = document.querySelector('.file-message');

    // Drag and drop styling
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        fileInput.files = dt.files;
        updateFileName();
    });

    fileInput.addEventListener('change', updateFileName);

    function updateFileName() {
        if (fileInput.files.length > 0) {
            if (fileInput.files.length === 1) {
                fileMsg.textContent = fileInput.files[0].name;
            } else {
                fileMsg.textContent = `${fileInput.files.length} files selected`;
            }
            fileMsg.style.color = '#66fcf1';
            const cancelBtn = document.getElementById('cancelUploadBtn');
            if(cancelBtn) cancelBtn.style.display = 'block';
        } else {
            fileMsg.textContent = 'Drag & drop or click to upload (.pdf, .docx, .png, .xlsx)';
            fileMsg.style.color = '';
            const cancelBtn = document.getElementById('cancelUploadBtn');
            if(cancelBtn) cancelBtn.style.display = 'none';
        }
    }

    const cancelUploadBtn = document.getElementById('cancelUploadBtn');
    if (cancelUploadBtn) {
        cancelUploadBtn.addEventListener('click', () => {
            fileInput.value = '';
            updateFileName();
        });
    }

    // Upload Handler
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (fileInput.files.length === 0) return;
        
        if (fileInput.files.length > 15) {
            alert('You can only upload a maximum of 15 files at a time.');
            return;
        }

        const formData = new FormData();
        for (let i = 0; i < fileInput.files.length; i++) {
            formData.append('files', fileInput.files[i]);
        }
        formData.append('session_id', sessionId);

        const btn = document.getElementById('uploadBtn');
        btn.textContent = 'Uploading...';
        btn.disabled = true;

        try {
            const res = await fetch('/upload', { 
                method: 'POST', 
                body: formData,
                headers: { 'X-Session-ID': sessionId }
            });
            const data = await res.json();
            
            if (res.ok) {
                statusMsg.textContent = 'Upload successful! Waiting for Eventarc...';
                statusMsg.style.color = 'var(--success)';
                fileInput.value = '';
                updateFileName();
                fileMsg.style.color = 'var(--text-primary)';
                
                // Reload page after a brief delay so the processing can finish and BQ reflects it
                setTimeout(() => window.location.reload(), 4000);
            } else {
                throw new Error(data.error || 'Upload failed');
            }
        } catch (error) {
            statusMsg.textContent = error.message;
            statusMsg.style.color = 'var(--danger)';
        } finally {
            btn.textContent = 'Upload to Pipeline';
            btn.disabled = false;
        }
    });

    // --- File Deletion ---
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            if (!confirm('Are you sure you want to delete this file?')) return;
            
            const filename = e.target.dataset.filename;
            e.target.textContent = '...';
            
            try {
                const res = await fetch(`/delete/${encodeURIComponent(filename)}`, { 
                    method: 'DELETE',
                    headers: { 'X-Session-ID': sessionId }
                });
                if (res.ok) {
                    // Remove row from table
                    e.target.closest('tr').remove();
                    updateDocCount();
                } else {
                    alert('Failed to delete file');
                    e.target.textContent = 'Delete';
                }
            } catch (error) {
                console.error(error);
                alert('Error connecting to server');
            }
        });
    });

    // --- Document Selection ---
    const selectAllCheckbox = document.getElementById('selectAllDocs');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
            document.querySelectorAll('.doc-checkbox').forEach(cb => {
                cb.checked = e.target.checked;
            });
        });
    }

    // --- Q&A Chat ---
    const qaForm = document.getElementById('qaForm');
    const chatHistory = document.getElementById('chatHistory');
    const questionInput = document.getElementById('questionInput');

    qaForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const question = questionInput.value.trim();
        if (!question) return;

        const selectedCheckboxes = document.querySelectorAll('.doc-checkbox:checked');
        const filenames = Array.from(selectedCheckboxes).map(cb => cb.value);

        // Removed restriction on empty filenames for MCP Agent mode

        // Add user msg
        addChatMsg(question, 'user');
        questionInput.value = '';

        // Add loading bot msg
        const loadingId = addChatMsg('<div class="spinner"></div>', 'bot');

        try {
            const res = await fetch('/ask', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Session-ID': sessionId
                },
                body: JSON.stringify({ question, filenames })
            });
            const data = await res.json();
            
            if (data.answer) {
                const msgElement = document.getElementById(loadingId);
                msgElement.innerHTML = marked.parse(data.answer);
                
                // Wrap tables for horizontal scroll
                msgElement.querySelectorAll('table').forEach(table => {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'table-wrapper';
                    table.parentNode.insertBefore(wrapper, table);
                    wrapper.appendChild(table);
                });

                // Check for tabular data (markdown table detection) or CSV code blocks
                const hasTable = data.answer.includes('|') && data.answer.includes('---');
                const hasCsv = data.answer.includes('```csv') || data.answer.includes('```text');
                
                if (hasTable || hasCsv) {
                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'export-actions';
                    
                    const excelBtn = document.createElement('button');
                    excelBtn.className = 'btn';
                    excelBtn.textContent = 'Export to Excel';
                    excelBtn.onclick = () => exportData(data.answer, 'excel');
                    
                    const pdfBtn = document.createElement('button');
                    pdfBtn.className = 'btn';
                    pdfBtn.textContent = 'Export to PDF';
                    pdfBtn.onclick = () => exportData(data.answer, 'pdf');
                    
                    actionsDiv.appendChild(excelBtn);
                    actionsDiv.appendChild(pdfBtn);
                    msgElement.appendChild(actionsDiv);
                }
            } else {
                document.getElementById(loadingId).textContent = "I'm sorry, I couldn't process that.";
            }
        } catch (error) {
            document.getElementById(loadingId).textContent = "Error communicating with the AI backend.";
        }
        
        chatHistory.scrollTop = chatHistory.scrollHeight;
    });

    function addChatMsg(text, sender) {
        const div = document.createElement('div');
        div.className = `msg ${sender}`;
        if (text.includes('<div class="spinner">')) {
            div.innerHTML = text;
        } else {
            div.textContent = text;
        }
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        div.id = id;
        chatHistory.appendChild(div);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return id;
    }

    async function exportData(content, format) {
        try {
            const res = await fetch('/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-ID': sessionId
                },
                body: JSON.stringify({ content, format })
            });
            if (!res.ok) throw new Error('Export failed');
            
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `DocuFlow_Export_${Date.now()}.${format === 'excel' ? 'xlsx' : 'pdf'}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (err) {
            alert('Error exporting data: ' + err.message);
        }
    }
});
