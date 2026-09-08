# ==============================================================================
# IMPORTAÇÃO DE PACOTES E BIBLIOTECAS
# ==============================================================================
import os
import calendar
import requests
from datetime import datetime, date
from pathlib import Path
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# Framework web Flask e utilitários de sessão/ciclo HTTP
from flask import Flask, request, render_template, redirect, session, flash, url_for
from flask_bcrypt import Bcrypt

# Conector nativo PostgreSQL com suporte a dicionários
import psycopg2
from psycopg2.extras import RealDictCursor

# Carrega prioritariamente o arquivo .env da raiz da aplicação
caminho_env = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=caminho_env)

# ==============================================================================
# CONFIGURAÇÕES DA APLICAÇÃO E SEGURANÇA
# ==============================================================================
app = Flask(__name__)

# Chave criptográfica obrigatória para assinar os cookies de sessão no navegador
app.secret_key = os.getenv("SECRET_KEY", "chave_secreta_academica_univesp_individual")

# Inicialização da extensão Bcrypt
bcrypt = Bcrypt(app)

# Diretório de armazenamento físico de anexos enviados pelos professores (PDF/Slides)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def obter_conexao():
    """
    Estabelece conexão com o PostgreSQL:
    Prioriza o Neon Serverless Cloud via DATABASE_URL do .env;
    caso ausente, recorre às credenciais locais como fallback.
    """
    url_banco = os.getenv("DATABASE_URL")
    if url_banco:
        return psycopg2.connect(url_banco)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "individual_gestao_escolar"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", "postgres"),
        port=os.getenv("DB_PORT", "5432")
    )


# ==============================================================================
# 1. AUTENTICAÇÃO, LOGIN E SESSÕES (RBAC)
# ==============================================================================

@app.route('/')
def index():
    """Despacha o usuário para o painel correspondente ao seu perfil ou para o login."""
    if 'id_usuario' in session:
        perfil = session.get('perfil_logado')
        if perfil == 'ADMIN':
            return redirect('/painel/admin')
        elif perfil == 'PROFESSOR':
            return redirect('/painel/professor')
        elif perfil == 'ALUNO':
            return redirect('/painel/aluno')
    return redirect('/login')


@app.route('/login')
def tela_login():
    """Exibe o template login.html"""
    return render_template('login.html')


@app.route('/fazer_login', methods=['POST'])
def fazer_login():
    """
    Autenticação com checagem de primeiro_acesso para troca obrigatória de senha.
    """
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            SELECT id_usuario, email, senha, perfil, primeiro_acesso 
            FROM usuarios 
            WHERE email = %s
        """, (email,))
        usuario = cursor.fetchone()

        if usuario and bcrypt.check_password_hash(usuario['senha'], senha):
            # Inicializa a sessão com os dados base
            session['id_usuario'] = usuario['id_usuario']
            session['email_logado'] = usuario['email']
            session['perfil_logado'] = str(usuario['perfil']).upper()

            # Se for primeiro acesso, redireciona para troca de senha obrigatória
            if usuario.get('primeiro_acesso'):
                flash("Este é o seu primeiro acesso. Por segurança, defina uma nova senha.")
                return redirect('/primeiro-acesso')

            # Mapeamento padrão para usuários regulares
            if session['perfil_logado'] == 'ADMIN':
                cursor.execute("SELECT id_admin FROM administradores WHERE id_usuario = %s", (usuario['id_usuario'],))
                adm = cursor.fetchone()
                session['id_perfil'] = adm['id_admin'] if adm else None
                return redirect('/painel/admin')

            elif session['perfil_logado'] == 'PROFESSOR':
                cursor.execute("SELECT id_professor FROM professores WHERE id_usuario = %s", (usuario['id_usuario'],))
                prof = cursor.fetchone()
                session['id_perfil'] = prof['id_professor'] if prof else None
                return redirect('/painel/professor')

            elif session['perfil_logado'] == 'ALUNO':
                cursor.execute("SELECT id_aluno FROM alunos WHERE id_usuario = %s", (usuario['id_usuario'],))
                aluno = cursor.fetchone()
                session['id_perfil'] = aluno['id_aluno'] if aluno else None
                return redirect('/painel/aluno')
        else:
            flash("E-mail ou senha incorretos.")
            return redirect('/login')

    except Exception as e:
        flash(f"Erro no processamento de login: {str(e)}")
        return redirect('/login')
    finally:
        cursor.close()
        conexao.close()


@app.route('/primeiro-acesso')
def tela_primeiro_acesso():
    """Tela obrigatória para redefinição da senha provisória."""
    if 'id_usuario' not in session:
        return redirect('/login')
    return render_template('primeiro_acesso.html')


@app.route('/salvar_nova_senha_primeiro_acesso', methods=['POST'])
def salvar_nova_senha_primeiro_acesso():
    """Grava a senha definitiva e remove o bloqueio de primeiro_acesso."""
    if 'id_usuario' not in session:
        return redirect('/login')

    id_usuario = session.get('id_usuario')
    nova_senha = request.form.get('nova_senha', '')
    confirma_senha = request.form.get('confirma_senha', '')

    if len(nova_senha) < 6:
        flash("A nova senha deve possuir no mínimo 6 caracteres.")
        return redirect('/primeiro-acesso')

    if nova_senha != confirma_senha:
        flash("As senhas informadas não coincidem.")
        return redirect('/primeiro-acesso')

    novo_hash = bcrypt.generate_password_hash(nova_senha).decode('utf-8')
    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    try:
        # Atualiza a senha e desliga a flag de primeiro_acesso
        cursor.execute("""
            UPDATE usuarios 
            SET senha = %s, primeiro_acesso = FALSE 
            WHERE id_usuario = %s
        """, (novo_hash, id_usuario))
        conexao.commit()

        # Busca o perfil para carregar o id_perfil e redirecionar para o painel correto
        cursor.execute("SELECT perfil FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        perfil = cursor.fetchone()['perfil']

        if perfil == 'PROFESSOR':
            cursor.execute("SELECT id_professor FROM professores WHERE id_usuario = %s", (id_usuario,))
            prof = cursor.fetchone()
            session['id_perfil'] = prof['id_professor'] if prof else None
            flash("Senha redefinida com sucesso! Bem-vindo(a) ao seu painel.")
            return redirect('/painel/professor')
        elif perfil == 'ALUNO':
            cursor.execute("SELECT id_aluno FROM alunos WHERE id_usuario = %s", (id_usuario,))
            aluno = cursor.fetchone()
            session['id_perfil'] = aluno['id_aluno'] if aluno else None
            flash("Senha cadastrada com sucesso!")
            return redirect('/painel/aluno')
        else:
            return redirect('/painel/admin')

    except Exception as e:
        conexao.rollback()
        flash(f"Falha ao redefinir a senha: {str(e)}")
        return redirect('/primeiro-acesso')
    finally:
        cursor.close()
        conexao.close()


@app.route('/logout')
def logout():
    """Limpa a sessão ativa e retorna ao login."""
    session.clear()
    flash("Sessão finalizada com sucesso.")
    return redirect('/login')


# ==============================================================================
# 2. MATRÍCULA E CADASTRO DE ALUNOS
# ==============================================================================

@app.route('/cadastro')
def pagina_cadastro_aluno():
    """Alimenta o select com os níveis acadêmicos via RealDictCursor."""
    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id_nivel, sigla, nome FROM niveis ORDER BY id_nivel ASC")
    niveis = cursor.fetchall()
    cursor.close()
    conexao.close()
    return render_template('cadastro_aluno.html', niveis=niveis)


@app.route('/salvar_cadastro_aluno', methods=['POST'])
def salvar_cadastro_aluno():
    """
    Cadastro realizado pelo próprio Aluno:
    Insere apenas em 'usuarios' e em 'alunos' com endereço completo.
    """
    dados = request.form
    email = dados.get('email', '').strip().lower()
    senha_plana = dados.get('senha', '')
    
    id_nivel_raw = dados.get('id_nivel')
    id_nivel = int(id_nivel_raw) if id_nivel_raw and str(id_nivel_raw).isdigit() else 1

    senha_hash = bcrypt.generate_password_hash(senha_plana).decode('utf-8')

    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        # Inserção das credenciais na tabela usuarios
        cursor.execute("""
            INSERT INTO usuarios (email, senha, perfil, primeiro_acesso)
            VALUES (%s, %s, 'ALUNO', FALSE)
            RETURNING id_usuario
        """, (email, senha_hash))
        id_usuario_criado = cursor.fetchone()[0]

        # Inserção dos dados cadastrais e endereço em alunos
        cursor.execute("""
            INSERT INTO alunos (
                id_usuario, id_nivel, nome, cpf, cep, logradouro, 
                bairro, cidade, uf, numero, complemento
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_aluno
        """, (
            id_usuario_criado, id_nivel, dados.get('nome'), dados.get('cpf'),
            dados.get('cep'), dados.get('logradouro'), dados.get('bairro'),
            dados.get('cidade'), dados.get('uf'), dados.get('numero'), dados.get('complemento')
        ))

        conexao.commit()
        flash("Matrícula realizada com sucesso! Faça seu login para acessar o sistema.")
        return redirect('/login')

    except psycopg2.IntegrityError as erro:
        conexao.rollback()
        msg_erro = str(erro)
        if 'usuarios_email_key' in msg_erro:
            flash("Erro: Este e-mail já está cadastrado no sistema.")
        elif 'alunos_cpf_key' in msg_erro:
            flash("Erro: Este CPF já se encontra registrado para outro aluno.")
        else:
            flash(f"Erro de integridade cadastral: {erro}")
        return redirect('/cadastro')
    except Exception as erro:
        conexao.rollback()
        flash(f"Falha ao salvar cadastro: {erro}")
        return redirect('/cadastro')
    finally:
        cursor.close()
        conexao.close()


# ==============================================================================
# 3. PAINEL DO ADMINISTRADOR
# ==============================================================================

@app.route('/painel/admin')
def painel_admin():
    """Dashboard administrativo com status financeiro categorizado e feriados nacionais."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)


    # Busca dos feriados nacionais via BrasilAPI
    ano_vigente = datetime.now().year
    feriados = []
    try:
        resp = requests.get(f"https://brasilapi.com.br/api/feriados/v1/{ano_vigente}", timeout=3)
        if resp.status_code == 200:
            feriados = resp.json()
    except Exception as e:
        print(f"Aviso BrasilAPI no painel admin: {e}")

    return render_template(
        'painel_admin.html', 
        feriados=feriados,
        ano_vigente=ano_vigente
    )




@app.route('/admin/cadastrar_professor', methods=['POST'])
def cadastrar_professor():
    """Cria novo professor associando usuarios.id_usuario a professores.id_usuario."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    nome = request.form.get('nome')
    email = request.form.get('email', '').strip().lower()
    senha_hash = bcrypt.generate_password_hash(request.form.get('senha')).decode('utf-8')

    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        cursor.execute("""
            INSERT INTO usuarios (email, senha, perfil) 
            VALUES (%s, %s, 'PROFESSOR') 
            RETURNING id_usuario
        """, (email, senha_hash))
        id_usuario = cursor.fetchone()[0]

        cursor.execute("INSERT INTO professores (id_usuario, nome) VALUES (%s, %s)", (id_usuario, nome))
        conexao.commit()
        flash(f"Professor(a) {nome} cadastrado com sucesso!")
    except psycopg2.IntegrityError:
        conexao.rollback()
        flash("Erro: Este e-mail institucional já está cadastrado.")
    finally:
        cursor.close()
        conexao.close()

    return redirect('/painel/admin')


@app.route('/admin/professores', methods=['GET'])
def gerenciar_professores():
    """Listagem de docentes cadastrados com dados institucionais e endereço."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT p.id_professor, p.id_usuario, p.nome, u.email,
               p.cep, p.logradouro, p.numero, p.complemento, p.bairro, p.cidade, p.uf
        FROM professores p
        JOIN usuarios u ON p.id_usuario = u.id_usuario
        ORDER BY p.nome ASC
    """)
    professores = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template('gerenciar_professores.html', professores=professores)

@app.route('/admin/cadastrar_evento', methods=['POST'])
def cadastrar_evento():
    """Publica comunicado no mural institucional."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    dados = request.form
    conexao = obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO eventos_agenda (titulo, descricao, data_evento, tipo_evento)
        VALUES (%s, %s, %s, %s)
    """, (dados.get('titulo'), dados.get('descricao'), dados.get('data_evento'), dados.get('tipo_evento')))
    
    conexao.commit()
    cursor.close()
    conexao.close()

    flash("Comunicado institucional publicado no mural acadêmico.")
    return redirect('/painel/admin')


# ==============================================================================
# 4. PAINEL DO PROFESSOR
# ==============================================================================

@app.route('/painel/professor')
def painel_professor():
    """Painel do Docente: grade, chamada, agendamento e calendário mensal interativo."""
    if session.get('perfil_logado') != 'PROFESSOR':
        return redirect('/login')

    id_usuario = session.get('id_usuario')
    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT id_professor FROM professores WHERE id_usuario = %s", (id_usuario,))
    docente = cursor.fetchone()
    if not docente:
        cursor.close()
        conexao.close()
        flash("Perfil docente não localizado.")
        return redirect('/login')

    id_professor = docente['id_professor']

    cursor.execute("""
        SELECT a.id_aula, a.data_aula, a.horario_inicio, 
               al.nome AS nome_aluno, n.sigla AS sigla_nivel,
               a.titulo_aula, t.titulo_tema, a.link_aula, a.status
        FROM aulas a
        JOIN alunos al ON a.id_aluno = al.id_aluno
        JOIN niveis n ON al.id_nivel = n.id_nivel
        LEFT JOIN temas t ON a.id_tema = t.id_tema
        WHERE a.id_professor = %s
        ORDER BY a.data_aula DESC, a.horario_inicio ASC
    """, (id_professor,))
    aulas = cursor.fetchall()

    cursor.execute("""
        SELECT al.id_aluno, al.nome, n.sigla AS sigla_nivel
        FROM alunos al
        JOIN niveis n ON al.id_nivel = n.id_nivel
        ORDER BY al.nome ASC
    """)
    alunos_disponiveis = cursor.fetchall()

    cursor.execute("""
        SELECT t.id_tema, t.titulo_tema, n.sigla AS sigla_nivel
        FROM temas t
        JOIN niveis n ON t.id_nivel = n.id_nivel
        ORDER BY t.titulo_tema ASC
    """)
    temas_disponiveis = cursor.fetchall()

    cursor.execute("SELECT id_nivel, nome, sigla FROM niveis ORDER BY id_nivel ASC")
    niveis = cursor.fetchall()

    hoje = date.today()
    try:
        ano_atual = int(request.args.get('ano', hoje.year))
        mes_atual = int(request.args.get('mes', hoje.month))
        if mes_atual < 1 or mes_atual > 12:
            ano_atual, mes_atual = hoje.year, hoje.month
    except (ValueError, TypeError):
        ano_atual, mes_atual = hoje.year, hoje.month

    ano_anterior, mes_anterior = (ano_atual - 1, 12) if mes_atual == 1 else (ano_atual, mes_atual - 1)
    ano_proximo, mes_proximo = (ano_atual + 1, 1) if mes_atual == 12 else (ano_atual, mes_atual + 1)

    cursor.execute("""
        SELECT a.id_aula, a.data_aula, a.horario_inicio, a.titulo_aula, a.status,
               al.nome AS nome_aluno
        FROM aulas a
        JOIN alunos al ON a.id_aluno = al.id_aluno
        WHERE a.id_professor = %s
          AND EXTRACT(YEAR FROM a.data_aula) = %s 
          AND EXTRACT(MONTH FROM a.data_aula) = %s
          AND a.status != 'CANCELADA'
    """, (id_professor, ano_atual, mes_atual))
    aulas_do_mes = cursor.fetchall()

    cursor.execute("""
        SELECT data_evento AS data, titulo, tipo_evento AS tipo, descricao
        FROM eventos_agenda
        WHERE EXTRACT(YEAR FROM data_evento) = %s AND EXTRACT(MONTH FROM data_evento) = %s
        ORDER BY data_evento ASC
    """, (ano_atual, mes_atual))
    eventos_locais = cursor.fetchall()

    cursor.close()
    conexao.close()

    feriados_nacionais = []
    try:
        resposta = requests.get(f"https://brasilapi.com.br/api/feriados/v1/{ano_atual}", timeout=3)
        if resposta.status_code == 200:
            for f in resposta.json():
                partes = f['date'].split('-')
                if int(partes[1]) == mes_atual:
                    feriados_nacionais.append({
                        'data': f['date'],
                        'titulo': f['name'],
                        'tipo': 'FERIADO_NACIONAL',
                        'descricao': 'Feriado Nacional Oficial'
                    })
    except Exception as erro:
        print(f"Aviso: BrasilAPI ({erro})")

    aulas_convertidas = []
    for a in aulas_do_mes:
        aulas_convertidas.append({
            'data': a['data_aula'],
            'titulo': f"{str(a['horario_inicio'])[:5]} - {a['nome_aluno']}",
            'tipo': 'AULA_DOCENTE',
            'descricao': f"{a['titulo_aula']} (Status: {a['status']})",
            'id_aula': a['id_aula']
        })

    calendario_unificado = list(eventos_locais) + feriados_nacionais + aulas_convertidas
    calendario_unificado.sort(key=lambda x: str(x['data']))

    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    matriz_mes = cal.monthdayscalendar(ano_atual, mes_atual)

    eventos_por_dia = {}
    for ev in calendario_unificado:
        data_ev = ev.get('data')
        dia_num = None
        if isinstance(data_ev, (datetime, date)):
            dia_num = data_ev.day
        elif isinstance(data_ev, str) and data_ev:
            partes = data_ev.split('-')
            if len(partes) == 3:
                dia_num = int(partes[2])

        if dia_num:
            if dia_num not in eventos_por_dia:
                eventos_por_dia[dia_num] = []
            eventos_por_dia[dia_num].append(ev)

    nomes_meses = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]

    return render_template(
        'painel_professor.html',
        aulas=aulas,
        alunos_disponiveis=alunos_disponiveis,
        temas_disponiveis=temas_disponiveis,
        niveis=niveis,
        calendario_unificado=calendario_unificado,
        matriz_mes=matriz_mes,
        eventos_por_dia=eventos_por_dia,
        ano_atual=ano_atual,
        mes_atual=mes_atual,
        nome_mes_atual=nomes_meses[mes_atual],
        ano_anterior=ano_anterior,
        mes_anterior=mes_anterior,
        ano_proximo=ano_proximo,
        mes_proximo=mes_proximo,
        dia_hoje=hoje.day if (hoje.year == ano_atual and hoje.month == mes_atual) else None
    )


@app.route('/professor/agendar_aula', methods=['POST'])
def agendar_aula():
    """Agendamento individual com validação de slot e uploads."""
    if session.get('perfil_logado') != 'PROFESSOR':
        return redirect('/login')

    dados = request.form
    id_professor = session.get('id_perfil')
    id_aluno = dados.get('id_aluno')
    id_tema = dados.get('id_tema') if dados.get('id_tema') else None

    url_pdf = None
    arquivo_pdf = request.files.get('arquivo_pdf')
    if arquivo_pdf and arquivo_pdf.filename != '':
        nome_pdf = secure_filename(f"aula_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo_pdf.filename}")
        arquivo_pdf.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_pdf))
        url_pdf = f"/static/uploads/{nome_pdf}"

    url_slides = None
    arquivo_slides = request.files.get('arquivo_slides')
    if arquivo_slides and arquivo_slides.filename != '':
        nome_slides = secure_filename(f"slides_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo_slides.filename}")
        arquivo_slides.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_slides))
        url_slides = f"/static/uploads/{nome_slides}"

    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        cursor.execute("""
            INSERT INTO aulas (
                id_professor, id_aluno, id_tema, titulo_aula, data_aula, 
                horario_inicio, link_aula, status, url_pdf, url_slides, observacoes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'AGENDADA', %s, %s, %s)
            RETURNING id_aula
        """, (
            id_professor, id_aluno, id_tema, dados.get('titulo_aula'),
            dados.get('data_aula'), dados.get('horario_inicio'), dados.get('link_aula'),
            url_pdf, url_slides, dados.get('observacoes')
        ))
        id_aula_criada = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO controle_academico (id_aluno, id_aula)
            VALUES (%s, %s)
        """, (id_aluno, id_aula_criada))

        conexao.commit()
        flash("Aula agendada com sucesso!")
    except psycopg2.IntegrityError:
        conexao.rollback()
        flash("Conflito de agenda: Você já possui uma aula marcada nesta mesma data e horário.")
    finally:
        cursor.close()
        conexao.close()

    return redirect('/painel/professor')


@app.route('/professor/cadastrar_tema', methods=['POST'])
def cadastrar_tema():
    """Inclusão de tema curricular associado ao nível pedagógico."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    dados = request.form
    conexao = obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO temas (id_nivel, titulo_tema, descricao)
        VALUES (%s, %s, %s)
    """, (dados.get('id_nivel'), dados.get('titulo_tema'), dados.get('descricao')))
    conexao.commit()

    cursor.close()
    conexao.close()

    flash("Tema pedagógico incluído no catálogo.")
    return redirect('/painel/professor')


# ==============================================================================
# 5. PAINEL DO ALUNO
# ==============================================================================

@app.route('/painel/aluno')
def painel_aluno():
    """Dashboard do estudante com status e calendário."""
    if session.get('perfil_logado') != 'ALUNO':
        flash("Acesso restrito a alunos.")
        return redirect('/login')

    id_aluno = session.get('id_perfil')
    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT a.nome, n.nome AS nivel
        FROM alunos a
        JOIN niveis n ON a.id_nivel = n.id_nivel
        WHERE a.id_aluno = %s
    """, (id_aluno,))
    dados_aluno = cursor.fetchone()



    cursor.execute("""
        SELECT a.id_aula, a.data_aula, a.horario_inicio, p.nome AS nome_professor,
               a.titulo_aula, t.titulo_tema, a.link_aula, a.status,
               COALESCE(ca.aula_assistida, FALSE) AS aula_assistida
        FROM aulas a
        JOIN professores p ON a.id_professor = p.id_professor
        LEFT JOIN temas t ON a.id_tema = t.id_tema
        LEFT JOIN controle_academico ca ON a.id_aula = ca.id_aula AND ca.id_aluno = a.id_aluno
        WHERE a.id_aluno = %s AND a.data_aula >= CURRENT_DATE AND a.status != 'CANCELADA'
        ORDER BY a.data_aula ASC, a.horario_inicio ASC
    """, (id_aluno,))
    proximas_aulas = cursor.fetchall()

    cursor.execute("""
        SELECT a.id_aula, a.data_aula, a.titulo_aula, ca.presenca, ca.aula_assistida,
               a.url_pdf, a.url_slides, ca.nota_professor, ca.nota_autoav
        FROM aulas a
        JOIN controle_academico ca ON a.id_aula = ca.id_aula
        WHERE a.id_aluno = %s
        ORDER BY a.data_aula DESC
    """, (id_aluno,))
    historico_aulas = cursor.fetchall()

    hoje = date.today()
    try:
        ano_atual = int(request.args.get('ano', hoje.year))
        mes_atual = int(request.args.get('mes', hoje.month))
        if mes_atual < 1 or mes_atual > 12:
            ano_atual, mes_atual = hoje.year, hoje.month
    except (ValueError, TypeError):
        ano_atual, mes_atual = hoje.year, hoje.month

    ano_anterior, mes_anterior = (ano_atual - 1, 12) if mes_atual == 1 else (ano_atual, mes_atual - 1)
    ano_proximo, mes_proximo = (ano_atual + 1, 1) if mes_atual == 12 else (ano_atual, mes_atual + 1)

    cursor.execute("""
        SELECT a.id_aula, a.data_aula, a.horario_inicio, a.titulo_aula, a.status,
               COALESCE(ca.aula_assistida, FALSE) AS assistida
        FROM aulas a
        LEFT JOIN controle_academico ca ON a.id_aula = ca.id_aula AND ca.id_aluno = a.id_aluno
        WHERE a.id_aluno = %s 
          AND EXTRACT(YEAR FROM a.data_aula) = %s 
          AND EXTRACT(MONTH FROM a.data_aula) = %s
          AND a.status != 'CANCELADA'
    """, (id_aluno, ano_atual, mes_atual))
    aulas_do_mes = cursor.fetchall()

    cursor.execute("""
        SELECT data_evento AS data, titulo, tipo_evento AS tipo, descricao
        FROM eventos_agenda
        WHERE EXTRACT(YEAR FROM data_evento) = %s AND EXTRACT(MONTH FROM data_evento) = %s
        ORDER BY data_evento ASC
    """, (ano_atual, mes_atual))
    eventos_locais = cursor.fetchall()

    cursor.close()
    conexao.close()

    feriados_nacionais = []
    try:
        resposta = requests.get(f"https://brasilapi.com.br/api/feriados/v1/{ano_atual}", timeout=3)
        if resposta.status_code == 200:
            for f in resposta.json():
                partes = f['date'].split('-')
                if int(partes[1]) == mes_atual:
                    feriados_nacionais.append({
                        'data': f['date'],
                        'titulo': f['name'],
                        'tipo': 'FERIADO_NACIONAL',
                        'descricao': 'Feriado Nacional Oficial'
                    })
    except Exception as erro:
        print(f"Aviso: BrasilAPI ({erro})")

    aulas_convertidas = []
    for a in aulas_do_mes:
        aulas_convertidas.append({
            'data': a['data_aula'],
            'titulo': f"{str(a['horario_inicio'])[:5]} - {a['titulo_aula']}",
            'tipo': 'AULA_ASSISTIDA' if a['assistida'] else 'AULA_AGENDADA',
            'descricao': f"Status: {'Assistida' if a['assistida'] else a['status']}",
            'id_aula': a['id_aula']
        })

    calendario_unificado = list(eventos_locais) + feriados_nacionais + aulas_convertidas
    calendario_unificado.sort(key=lambda x: str(x['data']))

    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    matriz_mes = cal.monthdayscalendar(ano_atual, mes_atual)

    eventos_por_dia = {}
    for ev in calendario_unificado:
        data_ev = ev.get('data')
        dia_num = None
        if isinstance(data_ev, (datetime, date)):
            dia_num = data_ev.day
        elif isinstance(data_ev, str) and data_ev:
            partes = data_ev.split('-')
            if len(partes) == 3:
                dia_num = int(partes[2])

        if dia_num:
            if dia_num not in eventos_por_dia:
                eventos_por_dia[dia_num] = []
            eventos_por_dia[dia_num].append(ev)

    nomes_meses = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]

    return render_template(
        'painel_aluno.html',
        dados_aluno=dados_aluno,
        proximas_aulas=proximas_aulas,
        historico_aulas=historico_aulas,
        calendario_unificado=calendario_unificado,
        matriz_mes=matriz_mes,
        eventos_por_dia=eventos_por_dia,
        ano_atual=ano_atual,
        mes_atual=mes_atual,
        nome_mes_atual=nomes_meses[mes_atual],
        ano_anterior=ano_anterior,
        mes_anterior=mes_anterior,
        ano_proximo=ano_proximo,
        mes_proximo=mes_proximo,
        dia_hoje=hoje.day if (hoje.year == ano_atual and hoje.month == mes_atual) else None
    )


# ==============================================================================
# 6. SALA VIRTUAL, DIÁRIO DE CLASSE E AUTOAVALIAÇÃO
# ==============================================================================

@app.route('/aula/<int:id_aula>')
def detalhe_aula(id_aula):
    """Exibe a sala virtual e diário com permissões dinâmicas."""
    if 'id_usuario' not in session:
        return redirect('/login')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT a.id_aula, a.id_aluno, a.titulo_aula, a.data_aula, a.horario_inicio, 
               p.nome AS nome_professor, al.nome AS nome_aluno, n.sigla AS nivel_aluno,
               t.titulo_tema, a.status, a.observacoes, a.link_aula, a.url_pdf, a.url_slides
        FROM aulas a
        JOIN professores p ON a.id_professor = p.id_professor
        JOIN alunos al ON a.id_aluno = al.id_aluno
        JOIN niveis n ON al.id_nivel = n.id_nivel
        LEFT JOIN temas t ON a.id_tema = t.id_tema
        WHERE a.id_aula = %s
    """, (id_aula,))
    aula = cursor.fetchone()

    cursor.execute("""
        SELECT presenca, aula_assistida, data_conclusao, nota_professor, nota_autoav, anotacoes_aluno
        FROM controle_academico
        WHERE id_aula = %s
    """, (id_aula,))
    controle = cursor.fetchone()

    cursor.close()
    conexao.close()

    if not aula:
        flash("Aula não localizada.")
        return redirect('/')

    return render_template('aula_detalhe.html', aula=aula, controle=controle)


@app.route('/aluno/salvar_autoavaliacao', methods=['POST'])
def salvar_autoavaliacao():
    """Salva visto de conclusão, anotações e autoavaliação do aluno."""
    if session.get('perfil_logado') != 'ALUNO':
        return redirect('/login')

    dados = request.form
    id_aula = dados.get('id_aula')
    nota_autoav = dados.get('nota_autoav')
    anotacoes = dados.get('anotacoes_aluno')

    conexao = obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE controle_academico
        SET aula_assistida = TRUE, 
            data_conclusao = CURRENT_TIMESTAMP, 
            nota_autoav = %s, 
            anotacoes_aluno = %s
        WHERE id_aula = %s AND id_aluno = %s
    """, (nota_autoav, anotacoes, id_aula, session.get('id_perfil')))
    conexao.commit()

    cursor.close()
    conexao.close()

    flash("Autoavaliação e anotações registradas com sucesso!")
    return redirect(f"/aula/{id_aula}")


@app.route('/professor/salvar_avaliacao_oficial', methods=['POST'])
def salvar_avaliacao_oficial():
    """Persiste a presença, nota oficial do professor e status da aula."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    dados = request.form
    id_aula = dados.get('id_aula')
    presenca = True if dados.get('presenca') == 'true' else False
    nota_professor = dados.get('nota_professor') if dados.get('nota_professor') else None
    novo_status = dados.get('status')

    conexao = obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE controle_academico
        SET presenca = %s, nota_professor = %s
        WHERE id_aula = %s
    """, (presenca, nota_professor, id_aula))

    cursor.execute("UPDATE aulas SET status = %s WHERE id_aula = %s", (novo_status, id_aula))

    conexao.commit()
    cursor.close()
    conexao.close()

    flash("Diário de classe atualizado com sucesso.")
    return redirect(f"/aula/{id_aula}")


# ==============================================================================
# 7. GERENCIADORES GERAIS (AULAS E ALUNOS)
# ==============================================================================

@app.route('/gerenciar-aulas', methods=['GET'])
def gerenciar_aulas():
    """Consulta de aulas com filtros de Nome do Aluno, Tema e Status."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    busca_aluno = request.args.get('busca_aluno')
    tema_id = request.args.get('tema_id')
    status = request.args.get('status')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT a.id_aula, a.data_aula, a.horario_inicio, al.nome AS nome_aluno,
               n.sigla AS sigla_nivel,
               p.nome AS nome_professor, t.titulo_tema, a.titulo_aula, a.status,
               a.id_tema, a.link_aula, a.observacoes
        FROM aulas a
        JOIN alunos al ON a.id_aluno = al.id_aluno
        JOIN niveis n ON al.id_nivel = n.id_nivel
        JOIN professores p ON a.id_professor = p.id_professor
        LEFT JOIN temas t ON a.id_tema = t.id_tema
        WHERE 1=1
    """
    parametros = []

    if session.get('perfil_logado') == 'PROFESSOR':
        query += " AND a.id_professor = %s"
        parametros.append(session.get('id_perfil'))

    if busca_aluno:
        query += " AND al.nome ILIKE %s"
        parametros.append(f"%{busca_aluno.strip()}%")
    if tema_id:
        query += " AND a.id_tema = %s"
        parametros.append(tema_id)
    if status:
        query += " AND a.status = %s"
        parametros.append(status)

    query += " ORDER BY a.data_aula DESC, a.horario_inicio DESC"
    cursor.execute(query, tuple(parametros))
    lista_aulas = cursor.fetchall()

    cursor.execute("""
        SELECT al.id_aluno, al.nome, n.sigla AS sigla_nivel 
        FROM alunos al 
        JOIN niveis n ON al.id_nivel = n.id_nivel 
        ORDER BY al.nome ASC
    """)
    alunos = cursor.fetchall()

    cursor.execute("""
        SELECT t.id_tema, t.titulo_tema, n.sigla AS sigla_nivel, t.descricao, t.url_pdf
        FROM temas t 
        JOIN niveis n ON t.id_nivel = n.id_nivel 
        ORDER BY t.titulo_tema ASC
    """)
    temas = cursor.fetchall()

    cursor.execute("SELECT id_nivel, sigla, nome FROM niveis ORDER BY id_nivel ASC")
    niveis = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template('gerenciar_aulas.html', lista_aulas=lista_aulas, alunos=alunos, temas=temas, niveis=niveis)


@app.route('/aulas/alterar_status', methods=['POST'])
def alterar_status_aula():
    """Modificação de status da aula."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    id_aula = request.form.get('id_aula')
    novo_status = request.form.get('novo_status')

    conexao = obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("UPDATE aulas SET status = %s WHERE id_aula = %s", (novo_status, id_aula))
    conexao.commit()
    cursor.close()
    conexao.close()

    flash(f"Status da aula {id_aula} alterado para {novo_status}.")
    return redirect('/gerenciar-aulas')


@app.route('/aulas/editar', methods=['POST'])
def editar_aula():
    """Reagendamento de aula."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    dados = request.form
    id_aula = dados.get('id_aula')
    id_tema = dados.get('id_tema') if dados.get('id_tema') else None

    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        cursor.execute("""
            UPDATE aulas
            SET data_aula = %s, horario_inicio = %s, id_tema = %s, 
                link_aula = %s, observacoes = %s
            WHERE id_aula = %s
        """, (
            dados.get('nova_data'), dados.get('novo_horario'), id_tema,
            dados.get('novo_link'), dados.get('observacoes'), id_aula
        ))
        conexao.commit()
        flash(f"Aula {id_aula} reagendada com sucesso!")
    except psycopg2.IntegrityError:
        conexao.rollback()
        flash("Erro de conflito: Professor já possui aula no horário indicado.")
    finally:
        cursor.close()
        conexao.close()

    return redirect('/gerenciar-aulas')


@app.route('/gerenciar-alunos', methods=['GET'])
def gerenciar_alunos():
    """
    Listagem de alunos com identificador padronizado u.id_usuario e filtros pedagógicos.
    """
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    busca_nome = request.args.get('busca_nome')
    nivel_id = request.args.get('nivel_id')
    aluno_edit_id = request.args.get('aluno_edit_id')
    
    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT a.id_aluno, a.id_usuario, a.id_nivel, a.nome, a.cpf, n.sigla AS sigla_nivel,
               u.email, a.cidade, a.uf, a.logradouro, a.numero, a.complemento, a.bairro, a.cep
        FROM alunos a
        JOIN usuarios u ON a.id_usuario = u.id_usuario
        JOIN niveis n ON a.id_nivel = n.id_nivel
        WHERE 1=1
    """
    params = []
    
    if busca_nome and busca_nome.strip():
        query += " AND a.nome ILIKE %s"
        params.append(f"%{busca_nome.strip()}%")

    if nivel_id and nivel_id.strip():
        query += " AND a.id_nivel = %s"
        params.append(nivel_id)

    query += " ORDER BY a.nome ASC"
    cursor.execute(query, tuple(params))
    alunos = cursor.fetchall()

    cursor.execute("SELECT id_nivel, sigla, nome FROM niveis ORDER BY id_nivel ASC")
    lista_niveis = cursor.fetchall()

    aluno_edicao = None
    if aluno_edit_id and session.get('perfil_logado') == 'ADMIN':
        cursor.execute("SELECT * FROM alunos WHERE id_aluno = %s", (aluno_edit_id,))
        aluno_edicao = cursor.fetchone()

    cursor.close()
    conexao.close()

    return render_template(
        'gerenciar_alunos.html', 
        alunos=alunos, 
        lista_niveis=lista_niveis, 
        aluno_edicao=aluno_edicao
    )


@app.route('/admin/alterar_nivel_aluno', methods=['POST'])
def alterar_nivel_aluno():
    """Reclassificação de nível pedagógico."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    id_aluno = request.form.get('id_aluno')
    novo_id_nivel = request.form.get('novo_id_nivel')

    conexao = obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("UPDATE alunos SET id_nivel = %s WHERE id_aluno = %s", (novo_id_nivel, id_aluno))
    conexao.commit()
    cursor.close()
    conexao.close()

    flash("Nível acadêmico do aluno atualizado.")
    return redirect('/gerenciar-alunos')




@app.route('/admin/excluir_aluno', methods=['POST'])
def excluir_aluno():
    """Exclui o usuário propagando a exclusão em cascata (DELETE por id_usuario)."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    id_usuario = request.form.get('id_usuario')

    conexao = obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
    conexao.commit()
    cursor.close()
    conexao.close()

    flash("Aluno e todos os seus históricos foram removidos com sucesso.")
    return redirect('/gerenciar-alunos')



@app.route('/admin/excluir_professor', methods=['POST'])
def excluir_professor():
    """Exclui o professor via id_usuario cascateando a exclusão."""
    if session.get('perfil_logado') != 'ADMIN':
        return redirect('/login')

    id_usuario = request.form.get('id_usuario')
    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        conexao.commit()
        flash("Professor removido com sucesso.")
    except Exception as e:
        conexao.rollback()
        flash(f"Não foi possível excluir o professor: {str(e)}")
    finally:
        cursor.close()
        conexao.close()

    return redirect('/admin/professores')

# ==============================================================================
# 8. CATÁLOGO CURRICULAR DE AULAS-MODELO
# ==============================================================================

@app.route('/catalogo-aulas', methods=['GET'])
def exibir_catalogo_aulas():
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    nivel_id = request.args.get('nivel_id')
    edit_id = request.args.get('edit_id')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT t.id_tema, t.id_nivel, t.titulo_tema, n.sigla AS sigla_nivel, t.descricao, 
               t.url_pdf, t.url_slides
        FROM temas t
        JOIN niveis n ON t.id_nivel = n.id_nivel
        WHERE 1=1
    """
    params = []
    if nivel_id:
        query += " AND t.id_nivel = %s"
        params.append(nivel_id)

    query += " ORDER BY t.id_nivel ASC, t.titulo_tema ASC"
    cursor.execute(query, tuple(params))
    temas = cursor.fetchall()

    tema_em_edicao = None
    if edit_id:
        cursor.execute("SELECT * FROM temas WHERE id_tema = %s", (edit_id,))
        tema_em_edicao = cursor.fetchone()

    cursor.execute("SELECT id_nivel, sigla, nome FROM niveis ORDER BY id_nivel ASC")
    niveis = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template('catalogo_aulas.html', temas=temas, niveis=niveis, tema_edicao=tema_em_edicao)


@app.route('/catalogo-aulas/cadastrar', methods=['POST'])
def cadastrar_aula_catalogo():
    """Upload e persistência de nova aula-modelo no catálogo."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    dados = request.form
    titulo_tema = dados.get('titulo_tema')
    id_nivel = dados.get('id_nivel')
    descricao = dados.get('descricao')

    url_pdf = None
    arquivo_pdf = request.files.get('arquivo_pdf')
    if arquivo_pdf and arquivo_pdf.filename != '':
        nome_pdf = secure_filename(f"tema_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo_pdf.filename}")
        arquivo_pdf.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_pdf))
        url_pdf = f"/static/uploads/{nome_pdf}"

    url_slides = None
    arquivo_slides = request.files.get('arquivo_slides')
    if arquivo_slides and arquivo_slides.filename != '':
        nome_slides = secure_filename(f"tema_slides_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo_slides.filename}")
        arquivo_slides.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_slides))
        url_slides = f"/static/uploads/{nome_slides}"

    conexao = obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO temas (id_nivel, titulo_tema, descricao, url_pdf, url_slides)
        VALUES (%s, %s, %s, %s, %s)
    """, (id_nivel, titulo_tema, descricao, url_pdf, url_slides))
    conexao.commit()

    cursor.close()
    conexao.close()

    flash("Nova aula-modelo incluída com sucesso no catálogo!")
    return redirect('/catalogo-aulas')


@app.route('/catalogo-aulas/excluir', methods=['POST'])
def excluir_aula_catalogo():
    """Remove a aula-modelo (ON DELETE SET NULL preserva aulas ministradas)."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    id_tema = request.form.get('id_tema')
    conexao = obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("DELETE FROM temas WHERE id_tema = %s", (id_tema,))
    conexao.commit()

    cursor.close()
    conexao.close()

    flash("Aula-modelo removida do catálogo.")
    return redirect('/catalogo-aulas')


@app.route('/conteudos/cadastrar', methods=['POST'])
def cadastrar_conteudo_modelo():
    """Cadastra a aula modelo a partir de gerenciar-aulas."""
    if session.get('perfil_logado') not in ['PROFESSOR', 'ADMIN']:
        return redirect('/login')

    dados = request.form
    titulo_tema = dados.get('titulo_tema')
    id_nivel = dados.get('id_nivel')
    descricao = dados.get('descricao')

    url_pdf = None
    arquivo_pdf = request.files.get('arquivo_pdf')
    if arquivo_pdf and arquivo_pdf.filename != '':
        nome_pdf = secure_filename(f"tema_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo_pdf.filename}")
        arquivo_pdf.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_pdf))
        url_pdf = f"/static/uploads/{nome_pdf}"

    url_slides = None
    arquivo_slides = request.files.get('arquivo_slides')
    if arquivo_slides and arquivo_slides.filename != '':
        nome_slides = secure_filename(f"tema_slides_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo_slides.filename}")
        arquivo_slides.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_slides))
        url_slides = f"/static/uploads/{nome_slides}"

    conexao = obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO temas (id_nivel, titulo_tema, descricao, url_pdf, url_slides)
        VALUES (%s, %s, %s, %s, %s)
    """, (id_nivel, titulo_tema, descricao, url_pdf, url_slides))
    conexao.commit()

    cursor.close()
    conexao.close()

    flash("Aula-modelo cadastrada no catálogo com sucesso!")
    return redirect('/gerenciar-aulas')

#============================================================================= ROTA DE SEGURANÇA
from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/meu-perfil', methods=['GET', 'POST'])
def meu_perfil():
    """Tela unificada para ADMIN, PROFESSOR e ALUNO gerenciarem seus dados e senha."""
    if 'id_usuario' not in session:
        return redirect('/login')

    id_usuario = session['id_usuario']
    perfil = session.get('perfil_logado')

    conexao = obter_conexao()
    cursor = conexao.cursor(cursor_factory=RealDictCursor)

    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')

        # Campos de endereço (se aplicável ao perfil)
        cep = request.form.get('cep')
        logradouro = request.form.get('logradouro')
        numero = request.form.get('numero')
        complemento = request.form.get('complemento')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        uf = request.form.get('uf')

        try:
            # 1. Validação e troca de senha (caso tenha preenchido)
            if nova_senha and nova_senha.strip():
                cursor.execute("SELECT senha_hash FROM usuarios WHERE id_usuario = %s", (id_usuario,))
                usuario_banco = cursor.fetchone()
                
                if not senha_atual or not check_password_hash(usuario_banco['senha_hash'], senha_atual):
                    flash("Senha atual incorreta. As alterações de senha não foram salvas.")
                    return redirect('/meu-perfil')
                
                nova_hash = generate_password_hash(nova_senha.strip())
                cursor.execute("UPDATE usuarios SET senha_hash = %s WHERE id_usuario = %s", (nova_hash, id_usuario))

            # 2. Atualização do e-mail de login
            cursor.execute("UPDATE usuarios SET email = %s WHERE id_usuario = %s", (email, id_usuario))
            session['email_logado'] = email

            # 3. Atualização na tabela específica do perfil
            if perfil == 'PROFESSOR':
                cursor.execute("""
                    UPDATE professores 
                    SET nome = %s, cep = %s, logradouro = %s, numero = %s, complemento = %s, bairro = %s, cidade = %s, uf = %s
                    WHERE id_usuario = %s
                """, (nome, cep, logradouro, numero, complemento, bairro, cidade, uf, id_usuario))
            elif perfil == 'ALUNO':
                cursor.execute("""
                    UPDATE alunos 
                    SET nome = %s, cep = %s, logradouro = %s, numero = %s, complemento = %s, bairro = %s, cidade = %s, uf = %s
                    WHERE id_usuario = %s
                """, (nome, cep, logradouro, numero, complemento, bairro, cidade, uf, id_usuario))

            conexao.commit()
            flash("Perfil atualizado com sucesso!")
        except Exception as e:
            conexao.rollback()
            flash(f"Erro ao salvar dados: {str(e)}")
        finally:
            cursor.close()
            conexao.close()

        return redirect('/meu-perfil')

    # Consulta dos dados atuais para preencher a tela (GET)
    if perfil == 'PROFESSOR':
        cursor.execute("""
            SELECT u.email, p.nome, p.cep, p.logradouro, p.numero, p.complemento, p.bairro, p.cidade, p.uf
            FROM usuarios u
            JOIN professores p ON u.id_usuario = p.id_usuario
            WHERE u.id_usuario = %s
        """, (id_usuario,))
    elif perfil == 'ALUNO':
        cursor.execute("""
            SELECT u.email, a.nome, a.cpf, n.nome AS nome_nivel, n.sigla AS sigla_nivel,
                   a.cep, a.logradouro, a.numero, a.complemento, a.bairro, a.cidade, a.uf
            FROM usuarios u
            JOIN alunos a ON u.id_usuario = a.id_usuario
            LEFT JOIN niveis n ON a.id_nivel = n.id_nivel
            WHERE u.id_usuario = %s
        """, (id_usuario,))
    else: # ADMIN
        cursor.execute("SELECT email, 'Administrador do Sistema' AS nome FROM usuarios WHERE id_usuario = %s", (id_usuario,))

    dados = cursor.fetchone()
    cursor.close()
    conexao.close()

    return render_template('meu_perfil.html', dados=dados, perfil=perfil)

# ==============================================================================
# INICIALIZAÇÃO DO SERVIDOR LOCAL
# ==============================================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)