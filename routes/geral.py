from flask import Blueprint, send_from_directory, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename

geral_bp = Blueprint('geral', __name__)

@geral_bp.route('/download/contrato/<filename>')
@login_required
def download_contrato(filename):
    filename = secure_filename(filename)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)