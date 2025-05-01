from flask import Flask, render_template, request, flash, redirect, session, g, url_for
from werkzeug.utils import secure_filename
import sqlite3
from flask_socketio import SocketIO, send
import phonenumbers
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'joaopedro'
app.config['DATABASE'] = 'usuarios.db'

socketio = SocketIO(app)

# Banco de dados
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db:
        db.close()

def create_table():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            senha TEXT NOT NULL,
            tema TEXT DEFAULT '#3b5998',
            img_perfil TEXT DEFAULT '/static/imagens/user.png',
            img_capa TEXT DEFAULT '/static/imagens/fundo.jpg',
            email TEXT NOT NULL UNIQUE,
            celular TEXT UNIQUE
        );
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            mensagem TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuario (id)
        );
    ''')
    db.commit()

with app.app_context():
    create_table()

# Validação de celular
def celular_valido(numero, pais='BR'):
    try:
        parsed = phonenumbers.parse(numero, pais)
        return phonenumbers.is_valid_number(parsed) and phonenumbers.number_type(parsed) == phonenumbers.PhoneNumberType.MOBILE
    except:
        return False

# Rotas
@app.route("/")
def login():
    return render_template('login.html')

@app.route("/cadastro")
def cadastro():
    return render_template("cadastro.html")

@app.route("/acesso", methods=['POST'])
def acesso():
    nome = request.form.get('email')
    senha = request.form.get('senha')

    db = get_db()
    usuario = db.execute('SELECT * FROM usuario WHERE (nome = ? OR email = ?) AND senha = ?', (nome, nome, senha)).fetchone()

    if usuario:
        session['id'] = usuario['id']
        return redirect('/home')
    else:
        flash('Nome de usuário ou senha incorretos, tente novamente!!')
        return redirect('/')

@app.route("/cadastrando", methods=['POST'])
def cadastrando():
    nome = request.form.get('nome')
    senha = request.form.get('senha')
    email = request.form.get('email')
    celular = request.form.get('celular')

    tema = '#3b5998'
    img_capa = '/static/imagens/Fundo.png'
    img_perfil = '/static/imagens/user.png'

    if not celular_valido(celular):
        flash('Número de celular inválido. Use o formato com DDD, ex: (11) 91234-5678.')
        return redirect('/cadastro')

    parsed = phonenumbers.parse(celular, 'BR')
    celular_formatado = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    db = get_db()
    existente = db.execute('SELECT * FROM usuario WHERE email = ? OR celular = ?', (email, celular_formatado)).fetchone()
    if existente:
        if existente['email'] == email:
            flash('Este e-mail já está em uso.')
        elif existente['celular'] == celular_formatado:
            flash('Este número de celular já está em uso.')
        return redirect('/cadastro')

    cursor = db.execute('''
        INSERT INTO usuario (nome, senha, tema, img_perfil, img_capa, email, celular)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (nome, senha, tema, img_perfil, img_capa, email, celular_formatado))
    db.commit()

    flash(f'Seja bem-vindo, {nome}!!')
    session['id'] = cursor.lastrowid
    return redirect('/home')

@app.route("/verificador")
def verificador():
    return render_template('verificador.html')

@app.route("/home")
def home():
    if 'id' in session:
        db = get_db()
        usuario = db.execute('SELECT * FROM usuario WHERE id = ?', (session['id'],)).fetchone()
        if usuario:
            return render_template('home.html',
                                   nome=usuario['nome'],
                                   tema=usuario['tema'],
                                   img_capa=usuario['img_capa'],
                                   img_perfil=usuario['img_perfil'])
        else:
            flash('Usuário não encontrado...')
    return redirect('/')

@app.route("/perfil")
def perfil():
    if 'id' in session:
        db = get_db()
        usuario = db.execute('SELECT * FROM usuario WHERE id = ?', (session['id'],)).fetchone()
        if usuario:
            return render_template('perfil.html',
                                   nome=usuario['nome'],
                                   email=usuario['email'],
                                   img_perfil=usuario['img_perfil'])
        else:
            flash("Usuário não encontrado.")
            return redirect('/')
    flash("Você precisa estar logado.")
    return redirect('/')


    foto_perfil = request.files.get('foto_perfil')
    foto_capa = request.files.get('foto_capa')

    db = get_db()
    usuario_id = session['id']
    atualizacoes = {}

    if foto_perfil and allowed_file(foto_perfil.filename):
        filename = secure_filename(f"perfil_{usuario_id}_" + foto_perfil.filename)
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto_perfil.save(caminho)
        atualizacoes['img_perfil'] = f'/static/uploads/{filename}'

    if foto_capa and allowed_file(foto_capa.filename):
        filename = secure_filename(f"capa_{usuario_id}_" + foto_capa.filename)
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto_capa.save(caminho)
        atualizacoes['img_capa'] = f'/static/uploads/{filename}'

    if atualizacoes:
        db.execute(f'''
            UPDATE usuario
            SET img_perfil = COALESCE(?, img_perfil),
                img_capa = COALESCE(?, img_capa)
            WHERE id = ?
        ''', (atualizacoes.get('img_perfil'), atualizacoes.get('img_capa'), usuario_id))
        db.commit()

        flash("Fotos atualizadas com sucesso!")
    else:
        flash("Nenhuma imagem válida foi enviada.")

    return redirect('/perfil')
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'foto_perfil' not in request.files:
        flash('Nenhuma imagem foi enviada.')
        return redirect('/perfil')
    
    file = request.files['foto_perfil']

    if file.filename == '':
        flash('Nome de arquivo inválido.')
        return redirect('/perfil')
    
    if file:
        filename = secure_filename(f"perfil_{session['id']}_{file.filename}")
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(caminho)
        
        db = get_db()
        db.execute('UPDATE usuario SET img_perfil = ? WHERE id = ?', (f'/static/uploads/{filename}', session['id']))
        db.commit()

        flash('Foto de perfil atualizada com sucesso!')
        return redirect('/perfil')

@app.route("/fotos")
def fotos():
    return render_template('fotos.html')

@app.route("/chat")
def chat():
    if 'id' in session:
        db = get_db()
        usuario = db.execute('SELECT * FROM usuario WHERE id = ?', (session['id'],)).fetchone()
        mensagens = db.execute('''
            SELECT m.mensagem, u.nome, m.timestamp 
            FROM mensagens m 
            JOIN usuario u ON m.usuario_id = u.id 
            ORDER BY m.timestamp ASC
        ''').fetchall()
        return render_template("chat.html", nome_usuario=usuario['nome'], mensagens=mensagens)
    return redirect('/')

@socketio.on('message')
def handle_message(msg):
    print(f'Mensagem recebida: {msg}')
    usuario_id = session.get('id')

    if usuario_id:
        msg_text = msg['text'] 
        db = get_db()
        db.execute('INSERT INTO mensagens (usuario_id, mensagem) VALUES (?, ?)', (usuario_id, msg_text))
        db.commit()
        usuario = db.execute('SELECT nome FROM usuario WHERE id = ?', (usuario_id,)).fetchone()
        send(f'{usuario["nome"]}: {msg_text}', broadcast=True)
    else:
        print("Usuário não autenticado para enviar mensagem.")


@app.route("/configuracoes")
def configuracoes():
    return render_template('configuracoes.html')

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    socketio.run(app, debug=True)
