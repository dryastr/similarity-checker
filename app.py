
from gensim.models.doc2vec import Doc2Vec
from flask import Flask, render_template, request, redirect, session, flash, url_for, send_file
import os
import re
import psycopg2
import pdfplumber
import spacy
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from docx import Document
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from auth import role_required
from app.helpers.file_helpers import extract_text_from_file

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'secret_key'

model = Doc2Vec.load('models/doc2vec_model')


def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="db_similarity",
        user="postgres",
        password="guitarflash215",
        port="5432"
    )
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(10) NOT NULL
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[2], password):

            session['user_id'] = user[0]
            session['username'] = username
            session['role'] = user[3]

            if user[3] == 'admin':
                return redirect('/home')
            else:
                return redirect('/dashboard')
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, hashed_password, role)
            )
            conn.commit()
            return redirect('/login')
        except psycopg2.IntegrityError:
            conn.rollback()
            return render_template('register.html', error='Username sudah ada')
        finally:
            cur.close()
            conn.close()

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/dashboard')
@role_required(['user'])
def dashboard():
    if 'username' not in session:
        return redirect('/login')
    return render_template('dashboard.html', username=session['username'], role=session['role'])


@app.route('/home')
@role_required(['admin'])
def home():
    if 'username' not in session:
        return redirect('/login')
    return render_template('home.html', username=session['username'], role=session['role'])


@app.route('/admin/upload', methods=['GET', 'POST'])
def admin_upload():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    if request.method == 'POST':
        title = request.form['title']
        file = request.files['file']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join('uploads', filename)
            file.save(filepath)

            file_text = extract_text_from_file(filepath)

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (title, file_name, file_text, vector) VALUES (%s, %s, %s, %s)",

                (title, filename, file_text, b'')
            )
            conn.commit()
            cur.close()
            conn.close()

            flash('Dokumen berhasil di-upload!', 'success')
            return redirect('/admin/upload')

    return render_template('admin/upload.html')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf', 'docx']


@app.route('/admin/documents')
def admin_documents():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM documents')
    documents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('admin/documents.html', documents=documents)


@app.route('/history-user')
def user_documents():
    if 'role' not in session or session['role'] != 'user':
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM history')
    documents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('user/documents.html', documents=documents)


INDONESIAN_STOPWORDS = set([
    'diperlukan', 'hendaknya', 'tapi', 'dimungkinkan', 'hendaklah', 'umumnya', 'tambahnya', 'usai', 'katakan', 'sebagaimana', 'sekali', 'persoalan', 'waduh', 'bermaksud', 'jelaslah', 'ditanyai', 'tiba', 'terdahulu', 'menghendaki', 'tidak', 'sangatlah', 'kalaulah', 'rata', 'tadi', 'sendirinya', 'tersampaikan', 'sekadar', 'mengakhiri', 'mempergunakan', 'sedikit', 'sekali-kali', 'katakanlah', 'karenanya', 'oleh', 'semampunya', 'diakhirinya', 'kapanpun', 'setidaknya', 'disini', 'menaiki', 'tentunya', 'terbanyak', 'tak', 'secara', 'diibaratkannya', 'mengatakan', 'hendak', 'dikarenakan', 'sekarang', 'berturut', 'ditanyakan', 'terlihat', 'diperlukannya', 'sebuah', 'cuma', 'ingat-ingat', 'sesegera', 'mengerjakan', 'keinginan', 'berlebihan', 'apalagi', 'siapapun', 'enggaknya', 'lagi', 'diungkapkan', 'bisa', 'tentu', 'bersiap', 'dia', 'ia', 'ini', 'dituturkan', 'mendatang', 'semacam', 'sebenarnya', 'terutama', 'diibaratkan', 'tunjuk', 'inilah', 'diri', 'seterusnya', 'menandaskan', 'kenapa', 'dimulailah', 'mengibaratkan', 'wong', 'disinilah', 'bahkan', 'kelihatan', 'sudahkah', 'mempertanyakan', 'dalam', 'luar', 'memulai', 'mengucapkan', 'selalu', 'waktu', 'ataukah', 'wahai', 'beberapa', 'semuanya', 'mampu', 'sebagainya', 'memungkinkan', 'bukannya', 'jadi', 'menanyakan', 'percuma', 'bolehkah', 'sekurang-kurangnya', 'yakin', 'memperbuat', 'jadinya', 'belumlah', 'terdiri', 'menjadi', 'sekalipun', 'merekalah', 'melihat', 'terakhir', 'hari', 'wah', 'sesuatu', 'sebelum', 'mendapat', 'berapa', 'dulu', 'sudah', 'tidaklah', 'kurang', 'makanya', 'ditunjuk', 'akhiri', 'bila', 'sayalah', 'buat', 'segalanya', 'berjumlah', 'perlunya', 'apatah', 'begitukah', 'itu', 'cara', 'antara', 'sampaikan', 'amat', 'mulailah', 'tertentu', 'setibanya', 'tiga', 'maka', 'semasih', 'nyaris', 'masalah', 'sebaik-baiknya', 'pasti', 'tiba-tiba', 'awal', 'bermula', 'tegasnya', 'bukanlah', 'selamanya', 'bermacam', 'satu', 'merupakan', 'disampaikan', 'sebanyak', 'menuturkan', 'segera', 'diucapkan', 'mendatangi', 'dipergunakan', 'bertanya-tanya', 'berkata', 'memintakan', 'jelas', 'kapan', 'tanyanya', 'tetapi', 'anda', 'benar', 'semula', 'sejenak', 'perlu', 'semakin', 'memang', 'begini', 'kemudian', 'serupa', 'disebutkan', 'pun', 'turut', 'bahwasanya', 'pastilah', 'nanti', 'didatangkan', 'dan', 'sedangkan', 'dikira', 'tentang', 'tersebutlah', 'diminta', 'dituturkannya', 'cukup', 'lanjutnya', 'dibuatnya', 'ucapnya', 'baru', 'haruslah', 'meminta', 'dijelaskan', 'kelihatannya', 'lainnya', 'ada', 'ibaratnya', 'ingin', 'menyangkut', 'mendapatkan', 'pentingnya', 'dirinya', 'dialah', 'diantaranya', 'terjadilah', 'ditujukan', 'bahwa', 'nah', 'mengibaratkannya', 'terhadap', 'saat', 'ditanya', 'ikut', 'mulanya', 'bakalan', 'setiba', 'tiap', 'bagaimana', 'sela', 'diberikannya', 'hanya', 'mengingat', 'meski', 'sebutlah', 'diinginkan', 'kata', 'hingga', 'usah', 'dikatakannya', 'apabila', 'per', 'manakala', 'untuk', 'sebegini', 'yakni', 'bertanya', 'olehnya', 'dipersoalkan', 'digunakan', 'ibu', 'teringat-ingat', 'adalah', 'berikan', 'sedemikian', 'sepihak', 'tandasnya', 'tegas', 'berlainan', 'bekerja', 'dini', 'inikah', 'mendatangkan', 'seringnya', 'terjadi', 'belakang', 'lalu', 'bawah', 'kedua', 'berada', 'jelaskan', 'bersiap-siap', 'awalnya', 'asal', 'daripada', 'mungkinkah', 'boleh', 'tutur', 'tengah', 'kasus', 'berikutnya', 'masing-masing', 'keadaan', 'terjadinya', 'meyakini', 'juga', 'ditunjuki', 'manalagi', 'menunjukkan', 'namun', 'bertutur', 'sehingga', 'terus', 'jadilah', 'ternyata', 'sama-sama', 'ditandaskan', 'ibaratkan', 'mirip', 'melihatnya', 'berkali-kali', 'ataupun', 'nyatanya', 'dimulai', 'bagi', 'jawabnya', 'teringat', 'aku', 'tambah', 'sudahlah', 'inginkah', 'seluruh', 'terasa', 'berakhirlah', 'dipertanyakan', 'kan', 'menyampaikan', 'saling', 'dimisalkan', 'sementara', 'beginikah', 'memastikan', 'walaupun', 'dibuat', 'kitalah', 'berkehendak', 'bilakah', 'ujar', 'pertanyakan', 'sendiri', 'jauh', 'dipunyai', 'tanpa', 'kamu', 'menyebutkan', 'berkeinginan', 'seseorang', 'pernah', 'beri', 'siapa', 'termasuk', 'pantas', 'pertama-tama', 'kelamaan', 'memperkirakan', 'semasa', 'didapat', 'belakangan', 'malahan', 'misal', 'mengungkapkan', 'yang', 'menunjuknya', 'setinggi', 'jika', 'sekalian', 'sepantasnyalah', 'kecil', 'masa', 'mau', 'bolehlah', 'lebih', 'lewat', 'betulkah', 'menanti', 'dimaksudnya', 'sebelumnya', 'jumlahnya', 'ditegaskan', 'bukan', 'di', 'mempersiapkan', 'sebesar', 'sekecil', 'bagaimanapun', 'sedikitnya', 'melalui', 'lamanya', 'benarlah', 'misalkan', 'kapankah', 'tetap', 'lagian', 'andalah', 'mengenai', 'mulai', 'mereka', 'bersama-sama', 'selama', 'ucap', 'soal', 'banyak', 'berawal', 'misalnya', 'nantinya', 'berdatangan', 'diketahui', 'jangan', 'suatu', 'biasa', 'seluruhnya', 'menantikan', 'atau', 'diberi', 'seingat', 'adapun', 'diantara', 'sering', 'ditambahkan', 'tuturnya', 'jikalau', 'berlalu', 'sebaliknya', 'begitupun', 'naik', 'diucapkannya', 'kelima', 'sepanjang', 'setiap', 'toh', 'itulah', 'sebaiknya', 'rasa', 'akhir', 'bagaikan', 'panjang', 'bagai', 'lanjut', 'benarkah', 'macam', 'sejumlah', 'menanya', 'semisalnya', 'serta', 'berujar', 'dekat', 'amatlah', 'artinya', 'bagaimanakah', 'khususnya', 'bersama', 'tandas', 'sebisanya', 'sejauh', 'sekitar', 'telah', 'balik', 'itukah', 'terlalu', 'dimaksudkan', 'sesekali', 'sebutnya', 'katanya', 'tidakkah', 'disebutkannya', 'sesudah', 'tampak', 'kalian', 'secukupnya', 'jawab', 'saya', 'masih', 'melakukan', 'pak', 'pula', 'dengan', 'menunjuk', 'sinilah', 'kembali', 'agaknya', 'antaranya', 'jelasnya', 'mengucapkannya', 'gunakan', 'diperkirakan', 'semua', 'tadinya', 'bermacam-macam', 'sebetulnya', 'jangankan', 'apaan', 'caranya', 'berapapun', 'demi', 'diperbuat', 'diperbuatnya', 'kira-kira', 'menginginkan', 'keterlaluan', 'tempat', 'bakal', 'menegaskan', 'tertuju', 'perlukah', 'sebaik', 'kita', 'agar', 'ketika', 'terkira', 'kalau', 'keseluruhannya', 'cukupkah', 'paling', 'seberapa', 'dua', 'selain', 'menyiapkan', 'setelah', 'justru', 'diingat', 'akulah', 'berkenaan', 'walau', 'lah', 'beginian', 'akhirnya', 'dikatakan', 'berapalah', 'soalnya', 'menurut', 'tanyakan', 'menjawab', 'seorang', 'ditunjukkannya', 'apakah', 'tersebut', 'makin', 'mengapa', 'sebagai', 'hanyalah', 'sebegitu', 'cukuplah', 'bukankah', 'sambil', 'dimaksudkannya', 'sesuatunya', 'selama-lamanya', 'sesama', 'hal', 'terdapat', 'apa', 'ialah', 'baik', 'belum', 'setidak-tidaknya', 'bulan', 'menambahkan', 'lama', 'masalahnya', 'mempersoalkan', 'melainkan', 'dahulu', 'berapakah', 'kiranya', 'demikian', 'lain', 'seperlunya', 'tentulah', 'meskipun', 'selaku', 'agak', 'diakhiri', 'saatnya', 'depan', 'dong', 'ungkapnya', 'guna', 'sedang', 'saja', 'kesampaian', 'berikut', 'memisalkan', 'penting', 'mengetahui', 'sekaligus', 'akankah', 'karena', 'pertanyaan', 'harus', 'kemungkinannya', 'semaunya', 'para', 'bung', 'keduanya', 'lima', 'jumlah', 'menyatakan', 'siap', 'kinilah', 'dipastikan', 'memerlukan', 'keluar', 'sama', 'sini', 'datang', 'selanjutnya', 'sajalah', 'sesaat', 'diingatkan', 'dimulainya', 'kalaupun', 'mengingatkan', 'harusnya', 'setempat', 'diperlihatkan', 'inginkan', 'mengatakannya', 'menjelaskan', 'entahlah', 'merasa', 'kini', 'ke', 'pertama', 'seolah-olah', 'berbagai', 'terhadapnya', 'jawaban', 'dapat', 'kebetulan', 'sesudahnya', 'berturut-turut', 'sangat', 'sampai', 'padanya', 'waktunya', 'menanyai', 'demikianlah', 'biasanya', 'betul', 'disebut', 'dilakukan', 'kemungkinan', 'pada', 'padahal', 'empat', 'beginilah', 'sempat', 'minta', 'menuju', 'ditunjuknya', 'se', 'sekurangnya', 'sekadarnya', 'pihak', 'dilihat', 'seolah', 'seperti', 'kepadanya', 'dimaksud', 'bagian', 'enggak', 'punya', 'keseluruhan', 'mampukah', 'adanya', 'tepat', 'menanti-nanti', 'begitulah', 'terlebih', 'maupun', 'sewaktu', 'rasanya', 'semata', 'menunjuki', 'dari', 'kamulah', 'sejak', 'kala', 'sekitarnya', 'begitu', 'seharusnya', 'kok', 'sampai-sampai', 'ditunjukkan', 'mengira', 'masing', 'supaya', 'diketahuinya', 'pukul', 'menyeluruh', 'semata-mata', 'berlangsung', 'tahun', 'diberikan', 'rupanya', 'tampaknya', 'menggunakan', 'atas', 'bisakah', 'tinggi', 'kamilah', 'mempunyai', 'pihaknya', 'berakhir', 'sepertinya', 'ujarnya', 'dikerjakan', 'sana', 'ungkap', 'berakhirnya', 'seketika', 'siapakah', 'umum', 'meyakinkan', 'sebabnya', 'membuat', 'dijelaskannya', 'kira', 'kepada', 'yaitu', 'seenaknya', 'malah', 'ibarat', 'janganlah', 'memihak', 'memberi', 'berarti', 'semampu', 'entah', 'sebut', 'segala', 'mungkin', 'memperlihatkan', 'sekiranya', 'hampir', 'tanya', 'berupa', 'sebagian', 'akan', 'semisal', 'besar', 'sebab', 'sesampai', 'dijawab', 'ingat', 'asalkan', 'sepantasnya', 'setengah', 'tahu', 'antar', 'dilalui', 'mana', 'seusai', 'masihkah', 'mula', 'memberikan', 'sendirian', 'kami', 'dimintai', 'bapak'
])


def mark_similar_words_in_original(original_text, similar_tokens):
    """
    Mencari dan menandai kata-kata dalam teks asli berdasarkan token yang similar

    Args:
        original_text (str): Teks asli dari dokumen
        similar_tokens (set): Kumpulan token yang dianggap similar

    Returns:
        list: Tuple berisi (kata, is_similar)
    """
    factory = StemmerFactory()
    stemmer = factory.create_stemmer()

    # Split teks asli dengan mempertahankan spasi dan tanda baca
    words = re.findall(r'\b\w+\b|\s+|[^\w\s]', original_text)

    marked_words = []
    for word in words:
        # Jika kata (bukan spasi atau tanda baca)
        if re.match(r'\b\w+\b', word):
            # Stem kata untuk pengecekan
            word_stem = stemmer.stem(word.lower())
            if word_stem in similar_tokens:
                marked_words.append((word, True))  # Word is similar
            else:
                marked_words.append((word, False))  # Word is not similar
        else:
            # Spasi atau tanda baca tetap dipertahankan
            marked_words.append((word, False))

    return marked_words

# Function untuk menghasilkan PDF dengan highlight


def create_highlighted_pdf(original_text, similar_tokens, output_path):
    """
    Membuat PDF baru dengan highlight pada kata-kata yang similar

    Args:
        original_text (str): Teks asli dari dokumen
        similar_tokens (set): Kumpulan token yang dianggap similar
        output_path (str): Path untuk menyimpan PDF hasil

    Returns:
        str: Path ke file PDF yang dihasilkan
    """
    marked_words = mark_similar_words_in_original(
        original_text, similar_tokens)

    # Buat PDF dengan reportlab
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=72, leftMargin=72,
        topMargin=72, bottomMargin=72
    )

    styles = getSampleStyleSheet()
    normal_style = styles["Normal"]

    # Define style untuk kata yang similar
    similar_style = ParagraphStyle(
        "Similar",
        parent=normal_style,
        backColor=colors.yellow,
    )

    # Gabungkan kata-kata menjadi paragraf dengan highlight
    content = []
    current_paragraph = ""

    for word, is_similar in marked_words:
        if is_similar:
            # Escape karakter khusus di HTML
            escaped_word = word.replace("&", "&amp;").replace(
                "<", "&lt;").replace(">", "&gt;")
            current_paragraph += f'<span backColor="yellow">{escaped_word}</span>'
        else:
            # Jika karakter spesial, langsung tambahkan
            current_paragraph += word

        # Jika newline, buat paragraf baru
        if word == '\n' or word == '\r\n':
            if current_paragraph:
                p = Paragraph(current_paragraph, normal_style)
                content.append(p)
                content.append(Spacer(1, 12))
                current_paragraph = ""

    # Tambahkan paragraf terakhir jika ada
    if current_paragraph:
        p = Paragraph(current_paragraph, normal_style)
        content.append(p)

    # Build PDF
    doc.build(content)

    return output_path

# Modifikasi function preprocess_text dan calculate_similarity untuk menyimpan token similar


def preprocess_text(text):
    factory = StemmerFactory()
    stemmer = factory.create_stemmer()
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    tokens = text.split()
    tokens = [word for word in tokens if word not in INDONESIAN_STOPWORDS]
    stemmed_tokens = [stemmer.stem(word) for word in tokens]
    return stemmed_tokens


def calculate_similarity(user_doc, db_docs):
    user_vector = model.infer_vector(preprocess_text(user_doc))
    user_tokens = preprocess_text(user_doc)
    user_token_count = len(user_tokens)
    similarities = []

    for db_doc in db_docs:
        db_vector = model.infer_vector(preprocess_text(db_doc['file_text']))
        similarity = model.docvecs.cosine_similarities(
            user_vector, [db_vector])[0]
        similarity = float(similarity)

        # Dapatkan token yang similar
        db_tokens = set(preprocess_text(db_doc['file_text']))
        user_tokens_set = set(user_tokens)
        similar_tokens = db_tokens.intersection(user_tokens_set)

        # Hitung jumlah token yang similar
        mark_count = len(similar_tokens)
        db_token_count = len(db_tokens)

        if db_token_count > 0:
            normalized_score = (mark_count / db_token_count) * 100
        else:
            normalized_score = 0

        normalized_score = min(normalized_score, 100)

        # Simpan set token yang similar
        similarities.append((db_doc['id'], normalized_score, similar_tokens))

    return sorted(similarities, key=lambda x: x[1], reverse=True)[:5]

# Tambahkan function untuk menyimpan file hasil ke sistem


def save_result_pdf(user_id, file_name, original_text, similar_tokens, doc_id):
    """
    Menyimpan hasil analisis sebagai PDF dengan highlight berdasarkan ID history.

    Args:
        user_id (int): ID user
        file_name (str): Nama file asli
        original_text (str): Teks asli dari dokumen
        similar_tokens (set): Kumpulan token yang dianggap similar
        doc_id (int): ID dokumen pembanding

    Returns:
        str: Path ke file PDF hasil
    """
    # Koneksi ke database
    conn = psycopg2.connect(
        "dbname=db_similarity user=postgres password=guitarflash215 host=localhost"
    )
    cur = conn.cursor()

    # Ambil ID terbaru dari history yang sesuai
    cur.execute(
        """
        SELECT id FROM history 
        WHERE user_id = %s AND document_id = %s AND uploaded_file_name = %s 
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, doc_id, file_name)
    )
    history_entry = cur.fetchone()

    if not history_entry:
        cur.close()
        conn.close()
        raise ValueError("History entry tidak ditemukan.")

    history_id = history_entry[0]  # Ambil ID history yang baru saja dibuat

    # Buat direktori jika belum ada
    result_dir = os.path.join(
        app.config['UPLOAD_FOLDER'], 'results', str(user_id))
    os.makedirs(result_dir, exist_ok=True)

    # Buat nama file PDF menggunakan ID history agar unik
    base_name = os.path.splitext(file_name)[0]
    result_file = os.path.join(result_dir, f"{base_name}_doc{history_id}.pdf")

    # Buat PDF dengan highlight
    create_highlighted_pdf(original_text, similar_tokens, result_file)

    # Perbarui history dengan path file hasil
    cur.execute(
        "UPDATE history SET result_file_path = %s WHERE id = %s",
        (result_file, history_id)
    )
    conn.commit()

    cur.close()
    conn.close()

    return result_file


def get_documents_from_db():
    conn = psycopg2.connect(
        "dbname=db_similarity user=postgres password=guitarflash215 host=localhost"
    )
    cur = conn.cursor()
    cur.execute("SELECT id, title, file_text, vector FROM documents")
    documents = cur.fetchall()
    cur.close()
    conn.close()
    return [{'id': doc[0], 'title': doc[1], 'file_text': doc[2], 'vector': doc[3]} for doc in documents]


def save_to_history(user_id, file_name, file_text, similarities):
    conn = psycopg2.connect(
        "dbname=db_similarity user=postgres password=guitarflash215 host=localhost"
    )
    cur = conn.cursor()

    # Simpan entry untuk setiap dokumen yang similar
    for doc_id, normalized_score, matched_text in similarities:
        cur.execute(
            "INSERT INTO history (user_id, document_id, uploaded_file_name, uploaded_file_text, similarity_score, matched_text) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, doc_id, file_name, file_text, normalized_score, matched_text)
        )

    conn.commit()
    cur.close()
    conn.close()


@app.route('/upload', methods=['GET'])
def upload_page():
    return render_template('upload-file.html')


@app.route('/check_similarity', methods=['POST'])
def check_similarity():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # Ekstrak konten dari file
    original_content = ""
    if filename.endswith('.txt'):
        with open(file_path, 'r') as f:
            original_content = f.read()
    elif filename.endswith('.docx'):
        doc = Document(file_path)
        original_content = "\n".join(
            [paragraph.text for paragraph in doc.paragraphs])
    elif filename.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            original_content = "\n".join([page.extract_text()
                                          for page in pdf.pages if page.extract_text()])

    db_docs = get_documents_from_db()
    similarities = calculate_similarity(original_content, db_docs)

    user_id = session.get('user_id')
    if not user_id:
        return "User ID tidak ditemukan. Silakan login terlebih dahulu.", 400

    # Simpan hasil ke history
    save_to_history(user_id, filename, original_content, [
                    (doc_id, score, "") for doc_id, score, tokens in similarities])

    # Untuk setiap dokumen yang similar, buat PDF dengan highlight
    result_files = []
    for doc_id, score, similar_tokens in similarities:
        # Ambil informasi dokumen dari database
        db_doc = next((doc for doc in db_docs if doc['id'] == doc_id), None)
        if db_doc:
            # Buat PDF dengan highlight - tambahkan doc_id untuk menghasilkan nama file unik
            result_file = save_result_pdf(
                user_id, filename, original_content, similar_tokens, doc_id)
            result_files.append((doc_id, score, result_file))

    # Render template dengan hasil dan path ke file PDF
    return render_template('similarity_results.html',
                           similarities=[(doc_id, score, os.path.basename(file_path))
                                         for doc_id, score, file_path in result_files])


def get_file_path(history_id=None, user_id=None, doc_id=None):
    """
    Mengambil path file dari database berdasarkan history_id atau kombinasi user_id & doc_id.

    Args:
        history_id (int, optional): ID dari history di database.
        user_id (int, optional): ID pengguna.
        doc_id (int, optional): ID dokumen.

    Returns:
        str: Path ke file PDF atau None jika tidak ditemukan.
    """
    # Koneksi ke database
    conn = psycopg2.connect(
        "dbname=db_similarity user=postgres password=guitarflash215 host=localhost"
    )
    cur = conn.cursor()

    if history_id:
        # Cari berdasarkan history_id langsung
        cur.execute(
            "SELECT result_file_path FROM history WHERE id = %s", (history_id,))
    elif user_id and doc_id:
        # Cari file terbaru berdasarkan user_id & doc_id
        cur.execute(
            """
            SELECT result_file_path 
            FROM history 
            WHERE user_id = %s AND document_id = %s AND result_file_path IS NOT NULL 
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, doc_id)
        )
    else:
        # Jika tidak ada parameter yang valid
        cur.close()
        conn.close()
        return None

    result = cur.fetchone()
    cur.close()
    conn.close()

    return result[0] if result else None

@app.route('/view/<int:history_id>')
def view_result(history_id):
    """
    Menampilkan file PDF berdasarkan history_id tanpa opsi download.
    """
    conn = psycopg2.connect(
        "dbname=db_similarity user=postgres password=guitarflash215 host=localhost"
    )
    cur = conn.cursor()

    # Ambil path file hasil dari history
    cur.execute("SELECT result_file_path FROM history WHERE id = %s", (history_id,))
    result = cur.fetchone()

    cur.close()
    conn.close()

    if result and result[0]:
        file_path = result[0]

        # Cek apakah file ada
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='application/pdf', as_attachment=False)
    
    # Jika file tidak ditemukan
    abort(404, description="File tidak ditemukan.") 

if __name__ == '__main__':
    init_db()
    print(app.url_map)
    app.run(debug=True)
