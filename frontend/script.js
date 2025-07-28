document.addEventListener('DOMContentLoaded', () => {
    const state = {
        pdfId: null,
    };

    const pdfUpload = document.getElementById('pdf-upload');
    const formSection = document.getElementById('form-section');
    const dynamicForm = document.getElementById('dynamic-form');
    const submitButton = document.getElementById('submit-form');
    const resultSection = document.getElementById('result-section');
    const downloadLink = document.getElementById('download-link');
    const errorMessage = document.getElementById('error-message');

    // Signature Pad setup
    const canvas = document.getElementById('signature-pad');
    const signaturePad = new SignaturePad(canvas, {
        backgroundColor: 'rgb(255, 255, 255)'
    });
    document.getElementById('clear-signature').addEventListener('click', () => {
        signaturePad.clear();
    });

    const displayError = (message) => {
        errorMessage.textContent = message;
        setTimeout(() => errorMessage.textContent = '', 5000);
    };

    pdfUpload.addEventListener('change', async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('pdf', file);

        try {
            const response = await fetch('http://127.0.0.1:5001/api/upload', {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to upload PDF.');
            }

            state.pdfId = data.pdfId;
            generateForm(data.fields);
            formSection.classList.remove('hidden');
            resultSection.classList.add('hidden');
            errorMessage.textContent = '';

        } catch (error) {
            displayError(error.message);
            formSection.classList.add('hidden');
        }
    });

    const generateForm = (fields) => {
        dynamicForm.innerHTML = ''; // Clear previous form
        fields.forEach(field => {
            // Note: /FT is the field type. We can use this for more specific inputs.
            // For simplicity, we'll use text inputs for most fields.
            // A production app would handle /Btn (checkboxes/radios), /Ch (choices), etc.
            const fieldName = field.name;
            if (fieldName.toLowerCase() === 'signature') {
                // This field will be handled by the canvas, so we don't create an input for it.
                return;
            }

            const fieldWrapper = document.createElement('div');
            fieldWrapper.className = 'form-field';

            const label = document.createElement('label');
            label.setAttribute('for', fieldName);
            label.textContent = fieldName;

            const input = document.createElement('input');
            input.type = 'text';
            input.id = fieldName;
            input.name = fieldName;
            input.value = field.value || '';

            fieldWrapper.appendChild(label);
            fieldWrapper.appendChild(input);
            dynamicForm.appendChild(fieldWrapper);
        });
    };

    submitButton.addEventListener('click', async () => {
        const formData = new FormData(dynamicForm);
        const data = Object.fromEntries(formData.entries());

        const payload = {
            pdfId: state.pdfId,
            formData: data,
            signature: signaturePad.isEmpty() ? null : signaturePad.toDataURL('image/png')
        };

        try {
            const response = await fetch('http://127.0.0.1:5001/api/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to generate PDF.');
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            downloadLink.href = url;
            resultSection.classList.remove('hidden');

        } catch (error) {
            displayError(error.message);
        }
    });
});
