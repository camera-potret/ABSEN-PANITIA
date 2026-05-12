import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import qrcode
import io
import base64
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('POSTGRES_URL', 'sqlite:///absen.db').replace('postgres://', 'postgresql://')
app.config['UPLOAD_FOLDER'] = 'app/static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

# Models
class Panitia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20)) # 'masuk', 'izin', None
    waktu = db.Column(db.DateTime)
    foto_izin = db.Column(db.Text)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wa_number = db.Column(db.String(20), default='628123456789')

# Create tables
with app.app_context():
    db.create_all()
    if not Settings.query.first():
        db.session.add(Settings())
        db.session.commit()

# Helper for QR Code
def generate_qr(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf)
    qr_bytes = buf.getvalue()
    return base64.b64encode(qr_bytes).decode('utf-8')

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    settings = Settings.query.first()
    if request.method == 'POST':
        if 'wa_number' in request.form:
            settings.wa_number = request.form['wa_number']
            db.session.commit()
            flash('Nomor WA berhasil diperbarui!', 'success')
        
        elif 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
                col_name = df.columns[0]
                
                # Hapus data lama agar tidak dobel saat re-upload
                Panitia.query.delete() 
                
                for name in df[col_name]:
                    if pd.notna(name):
                        new_p = Panitia(nama=str(name).strip())
                        db.session.add(new_p)
                db.session.commit()
                flash('Data panitia berhasil diperbarui!', 'success')

    panitia_list = Panitia.query.all()
    # Generate QR for the attendance link (base URL + /absen)
    base_url = request.url_root.rstrip('/')
    qr_code = generate_qr(f"{base_url}/absen")
    
    return render_template('dashboard.html', panitia=panitia_list, settings=settings, qr_code=qr_code)

@app.route('/absen')
def absen_landing():
    return render_template('attendance_select.html')

@app.route('/masuk', methods=['GET', 'POST'])
def masuk():
    if request.method == 'POST':
        nama_id = request.form.get('nama_id')
        p = Panitia.query.get(nama_id)
        if p and not p.status:
            p.status = 'masuk'
            p.waktu = datetime.now()
            db.session.commit()
            return render_template('status.html', success=True, message="Berhasil masuk!")
        return render_template('status.html', success=False, message="Gagal! Nama sudah dipilih atau tidak ditemukan.")
    
    # Only show panitia who haven't selected status yet
    available_panitia = Panitia.query.filter_by(status=None).all()
    return render_template('masuk.html', panitia=available_panitia)

@app.route('/izin', methods=['GET', 'POST'])
def izin():
    settings = Settings.query.first()
    if request.method == 'POST':
        nama_id = request.form.get('nama_id')
        alasan = request.form.get('alasan_izin')
        
        p = Panitia.query.get(nama_id)
        
        if p and not p.status:
            p.status = 'izin'
            p.waktu = datetime.now()
            p.foto_izin = alasan
            db.session.commit()
            
            # WhatsApp redirect
            msg = f"Halo, saya {p.nama} izin panitia dengan alasan: {alasan}"
            wa_url = f"https://wa.me/{settings.wa_number}?text={msg}"
            return redirect(wa_url)
        
        return render_template('status.html', success=False, message="Nama sudah dipilih atau tidak ditemukan.")

    available_panitia = Panitia.query.filter_by(status=None).all()
    return render_template('izin.html', panitia=available_panitia)

@app.route('/api/status')
def api_status():
    panitia_list = Panitia.query.all()
    data = []
    for p in panitia_list:
        data.append({
            'id': p.id,
            'nama': p.nama,
            'status': p.status,
            'waktu': p.waktu.strftime('%H:%M:%S') if p.waktu else '-',
            'alasan': p.foto_izin if p.foto_izin else None
        })
    return jsonify(data)

@app.route('/export/excel')
def export_excel():
    panitia_list = Panitia.query.all()
    data = []
    for p in panitia_list:
        data.append({
            'Nama': p.nama,
            'Status': p.status if p.status else '-',
            'Waktu': p.waktu.strftime('%H:%M:%S') if p.waktu else '-',
            'Alasan': p.foto_izin if p.foto_izin else '-',
        })
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Absensi')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"Absensi_Panitia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

@app.route('/export/qr')
def export_qr():
    base_url = request.url_root.rstrip('/')
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(f"{base_url}/absen")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name="QR_Absen_Panitia.png")

@app.route('/reset', methods=['POST'])
def reset_data():
    Panitia.query.delete()
    db.session.commit()
    flash('Semua data panitia telah dihapus!', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
