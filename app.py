
from gensim.models.doc2vec import Doc2Vec
from flask import Flask, render_template, request, redirect, session, flash, url_for
import os
import re
import psycopg2
import pdfplumber
import spacy
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


def preprocess_text(text):
    factory = StemmerFactory()
    stemmer = factory.create_stemmer()
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    tokens = text.split()
    tokens = [word for word in tokens if word not in INDONESIAN_STOPWORDS]
    stemmed_tokens = [stemmer.stem(word) for word in tokens]
    return stemmed_tokens


def highlight_similar_parts(text1, text2):
    tokens1 = set(preprocess_text(text1))
    tokens2 = preprocess_text(text2)

    highlighted = []
    mark_count = 0
    for token in tokens2:
        if token in tokens1:
            highlighted.append(f"<mark>{token}</mark>")
            mark_count += 1
        else:
            highlighted.append(token)

    return " ".join(highlighted), mark_count


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
        matched_text, mark_count = highlight_similar_parts(
            user_doc, db_doc['file_text'])
        db_tokens = preprocess_text(db_doc['file_text'])
        db_token_count = len(db_tokens)

        if db_token_count > 0:
            normalized_score = (mark_count / db_token_count) * 100
        else:
            normalized_score = 0

        normalized_score = min(normalized_score, 100)

        similarities.append((db_doc['id'], normalized_score, matched_text))

    return sorted(similarities, key=lambda x: x[1], reverse=True)[:5]


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
    for doc_id, normalized_score, matched_text in similarities:
        cur.execute(
            "INSERT INTO history (user_id, document_id, uploaded_file_name, uploaded_file_text, similarity_score, matched_text) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
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

    if filename.endswith('.txt'):
        with open(file_path, 'r') as f:
            content = f.read()
    elif filename.endswith('.docx'):
        doc = Document(file_path)
        content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    elif filename.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            content = "\n".join([page.extract_text()
                                for page in pdf.pages if page.extract_text()])

    db_docs = get_documents_from_db()
    similarities = calculate_similarity(content, db_docs)

    user_id = session.get('user_id')
    if not user_id:
        return "User ID tidak ditemukan. Silakan login terlebih dahulu.", 400

    save_to_history(user_id, filename, content, similarities)

    return render_template('similarity_results.html', similarities=similarities)


if __name__ == '__main__':
    init_db()
    print(app.url_map)
    app.run(debug=True)
