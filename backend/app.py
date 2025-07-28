import os
import uuid
import json
import base64
import io

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PyPDF2 import PdfReader, PdfWriter, Transformation
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)
CORS(app)

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated'
DATABASE_FILE = 'db.json'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# --- Database Helper ---
def get_db():
    """Reads the entire database from the JSON file."""
    if not os.path.exists(DATABASE_FILE):
        return {}
    with open(DATABASE_FILE, 'r') as f:
        # Return an empty dict if the file is empty
        return json.load(f) if os.path.getsize(DATABASE_FILE) > 0 else {}

def update_db(data):
    """Writes the entire database to the JSON file."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- API Endpoints ---

@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    """
    Handles PDF upload, extracts form fields, and returns them as JSON.
    """
    if 'pdf' not in request.files:
        return jsonify({"error": "No PDF file provided"}), 400

    file = request.files['pdf']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Invalid file. Please upload a PDF."}), 400

    # Generate a unique ID for this PDF session
    pdf_id = str(uuid.uuid4())
    original_path = os.path.join(UPLOAD_FOLDER, f"{pdf_id}.pdf")
    file.save(original_path)

    try:
        reader = PdfReader(original_path)
        fields = reader.fields
        
        if not fields:
             return jsonify({"error": "This PDF does not contain any fillable form fields."}), 400

        field_details = []
        for name, properties in fields.items():
            field_details.append({
                "name": name,
                # Field properties can be PyPDF2 objects, not just strings.
                # We must cast them to strings to ensure they are JSON-serializable.
                "type": str(properties.get('/FT', 'unknown')),
                "value": str(properties.get('/V', ''))
            })

        return jsonify({"pdfId": pdf_id, "fields": field_details})

    except Exception as e:
        return jsonify({"error": f"Failed to process PDF: {str(e)}"}), 500


@app.route('/api/submit', methods=['POST'])
def submit_form():
    """
    Receives form data, fills the PDF, saves data to DB, and returns the filled PDF.
    """
    data = request.get_json()
    pdf_id = data.get('pdfId')
    form_data = data.get('formData')
    signature_data_url = data.get('signature')

    if not all([pdf_id, form_data]):
        return jsonify({"error": "Missing pdfId or formData"}), 400

    original_path = os.path.join(UPLOAD_FOLDER, f"{pdf_id}.pdf")
    if not os.path.exists(original_path):
        return jsonify({"error": "Original PDF not found. Please upload again."}), 404

    try:
        # --- Fill PDF Form Fields ---
        reader = PdfReader(original_path)
        writer = PdfWriter()
        writer.append(reader)

        # More efficient method to fill all form fields at once
        writer.update_form_field_values(form_data)
        # --- Stamp Signature if provided (with correct placement and scaling) ---
        if signature_data_url:
            # Decode the base64 signature image
            img_data = base64.b64decode(signature_data_url.split(',')[1])
            img = Image.open(io.BytesIO(img_data))
            
            # Create a temporary PDF with just the image
            img_pdf_buffer = io.BytesIO()
            
            # Find the signature field location to correctly place and scale the signature
            signature_field_found = False
            for page_num, page in enumerate(reader.pages):
                if signature_field_found: break
                for annot in page.get('/Annots', []):
                    field = annot.get_object()
                    # Look for a field named 'Signature' (case-insensitive)
                    if field.get('/T', '').lower() == 'signature':
                        rect = field.get('/Rect') # [x0, y0, x1, y1]
                        if not rect: continue

                        # --- Create a new PDF "stamp" with the signature ---
                        sig_field_w, sig_field_h = float(rect[2] - rect[0]), float(rect[3] - rect[1])
                        
                        # Preserve aspect ratio of the signature image
                        img_w, img_h = img.size
                        aspect = img_h / img_w # In Python 3, / is float division
                        final_w = sig_field_w
                        final_h = final_w * aspect
                        if final_h > sig_field_h:
                            final_h = sig_field_h
                            final_w = final_h / aspect
                        
                        # Center the image in the field
                        x_offset = (sig_field_w - final_w) / 2
                        y_offset = (sig_field_h - final_h) / 2

                        packet = io.BytesIO()
                        can = canvas.Canvas(packet, pagesize=(sig_field_w, sig_field_h))
                        can.drawImage(ImageReader(img), x_offset, y_offset, width=final_w, height=final_h, mask='auto')
                        can.save()
                        packet.seek(0)
                        
                        signature_stamp_pdf = PdfReader(packet)
                        stamp_page = signature_stamp_pdf.pages[0]
                        
                        # --- Merge the stamp onto the target page ---
                        op = Transformation().translate(tx=float(rect[0]), ty=float(rect[1]))
                        stamp_page.add_transformation(op)
                        writer.pages[page_num].merge_page(stamp_page)
                        
                        signature_field_found = True
                        break

        # --- Save the filled PDF ---
        filled_path = os.path.join(GENERATED_FOLDER, f"filled_{pdf_id}.pdf")
        with open(filled_path, "wb") as output_stream:
            writer.write(output_stream)

        # --- Save data to our JSON "database" ---
        db = get_db()
        db[pdf_id] = form_data
        update_db(db)

        return send_file(filled_path, as_attachment=True)

    except Exception as e:
        return jsonify({"error": f"An error occurred while filling the PDF: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
