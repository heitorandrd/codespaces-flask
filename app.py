import json
import os
import re
import secrets
import struct
import threading
import zlib
from datetime import datetime
from functools import wraps
from math import isfinite

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------
# Caminhos e configurações
# ---------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '.env')
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'database.json')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOAD_DIR = os.path.join(STATIC_DIR, 'uploads')
AVATAR_PADRAO = 'static/images/default_avatar.png'
TAMANHO_MAX_UPLOAD = 2 * 1024 * 1024  # 2 MB


def carregar_env():
    """Lê o arquivo .env (formato CHAVE=valor) e cria o que estiver faltando.

    Na primeira execução o app gera sozinho uma SECRET_KEY forte e aleatória
    e a senha do administrador padrão, e grava tudo no .env (que o .gitignore ignora).
    """
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding='utf-8') as arquivo:
            for linha in arquivo:
                linha = linha.strip()
                if linha and not linha.startswith('#') and '=' in linha:
                    chave, valor = linha.split('=', 1)
                    valor = valor.strip().strip('"\'')
                    if valor:
                        os.environ.setdefault(chave.strip(), valor)

    padroes = [
        ('SECRET_KEY', secrets.token_hex(32)),
        ('ADMIN_EMAIL', 'admin@portal.com'),
        ('ADMIN_SENHA', secrets.token_urlsafe(9)),
        ('PERMITIR_ADMIN_NO_CADASTRO', '1'),  # 1 = o cadastro mostra a opção "Admin"; 0 = esconde
    ]
    novos = [(chave, valor) for chave, valor in padroes if not os.environ.get(chave)]
    if novos:
        precisa_quebra = False
        if os.path.exists(ENV_PATH) and os.path.getsize(ENV_PATH) > 0:
            with open(ENV_PATH, 'rb') as arquivo:
                arquivo.seek(-1, os.SEEK_END)
                precisa_quebra = arquivo.read(1) != b'\n'
        with open(ENV_PATH, 'a', encoding='utf-8') as arquivo:
            if precisa_quebra:
                arquivo.write('\n')
            for chave, valor in novos:
                arquivo.write('%s=%s\n' % (chave, valor))
                os.environ[chave] = valor


carregar_env()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']  # assina o cookie da sessão (impede adulteração)
app.config['MAX_CONTENT_LENGTH'] = TAMANHO_MAX_UPLOAD
app.config['SESSION_COOKIE_HTTPONLY'] = True   # o JavaScript não consegue ler o cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # o cookie não vai em formulários de outros sites


# ---------------------------------------------------------------
# Recursos gerados automaticamente (só se ainda não existirem)
# ---------------------------------------------------------------
def _cobertura(distancia):
    """Suaviza a borda: 1 dentro da forma, 0 fora e valores intermediários na borda."""
    return max(0.0, min(1.0, 0.5 - distancia))


def _desenhar_icone(tamanho, tipo):
    """Desenha um ícone redondo verde e devolve as linhas de pixels RGBA."""
    verde, branco = (32, 110, 90), (255, 255, 255)
    centro = tamanho / 2
    linhas = []
    for y in range(tamanho):
        linha = bytearray()
        for x in range(tamanho):
            px, py = x + 0.5, y + 0.5
            fundo = _cobertura(((px - centro) ** 2 + (py - centro) ** 2) ** 0.5 - centro)
            if tipo == 'avatar':  # cabeça + ombros
                cabeca = _cobertura(((px - centro) ** 2 + (py - tamanho * 0.38) ** 2) ** 0.5 - tamanho * 0.18)
                elipse = (((px - centro) / (tamanho * 0.31)) ** 2 + ((py - tamanho * 0.92) / (tamanho * 0.30)) ** 2) ** 0.5
                forma = max(cabeca, _cobertura((elipse - 1) * tamanho * 0.30))
            else:  # logo: cruz da saúde
                horizontal = _cobertura(max(abs(px - centro) - tamanho * 0.26, abs(py - centro) - tamanho * 0.08))
                vertical = _cobertura(max(abs(px - centro) - tamanho * 0.08, abs(py - centro) - tamanho * 0.26))
                forma = max(horizontal, vertical)
            rgb = [round(v * (1 - forma) + b * forma) for v, b in zip(verde, branco)]
            linha += bytes(rgb + [round(255 * fundo)])
        linhas.append(bytes(linha))
    return linhas


def _png(tamanho, tipo):
    """Monta um arquivo PNG (sem bibliotecas externas) a partir do desenho."""
    bruto = b''.join(b'\x00' + linha for linha in _desenhar_icone(tamanho, tipo))

    def bloco(nome, dados):
        corpo = nome + dados
        return struct.pack('>I', len(dados)) + corpo + struct.pack('>I', zlib.crc32(corpo) & 0xffffffff)

    return (b'\x89PNG\r\n\x1a\n'
            + bloco(b'IHDR', struct.pack('>IIBBBBB', tamanho, tamanho, 8, 6, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(bruto, 9))
            + bloco(b'IEND', b''))


def garantir_recursos():
    """Cria as pastas e os arquivos padrão (avatar, logo e favicon) caso não existam."""
    pastas = [DATA_DIR, UPLOAD_DIR, os.path.join(STATIC_DIR, 'images'), os.path.join(STATIC_DIR, 'icons')]
    for pasta in pastas:
        os.makedirs(pasta, exist_ok=True)

    avatar = os.path.join(STATIC_DIR, 'images', 'default_avatar.png')
    if not os.path.exists(avatar):
        with open(avatar, 'wb') as arquivo:
            arquivo.write(_png(192, 'avatar'))

    logo = os.path.join(STATIC_DIR, 'images', 'logo.png')
    if not os.path.exists(logo):
        with open(logo, 'wb') as arquivo:
            arquivo.write(_png(128, 'logo'))

    favicon = os.path.join(STATIC_DIR, 'icons', 'favicon.ico')
    if not os.path.exists(favicon):
        png = _png(32, 'logo')
        cabecalho = struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 32, 32, 0, 0, 1, 32, len(png), 22)
        with open(favicon, 'wb') as arquivo:
            arquivo.write(cabecalho + png)


# ---------------------------------------------------------------
# Dados fixos
# ---------------------------------------------------------------
FUNCOES = {'comum': 'Comum', 'admin': 'Administrador'}

SEXOS = {'masculino': 'Masculino', 'feminino': 'Feminino', 'outro': 'Outro'}

EQUIPE = [
    {'nome': 'Diego', 'papel': 'Aluno'},
    {'nome': 'Gustavo', 'papel': 'Aluno'},
    {'nome': 'Heitor', 'papel': 'Aluno'},
    {'nome': 'Kauanny', 'papel': 'Aluna'},
]

METAS = [
    'Calcular o IMC mensalmente',
    'Praticar atividade física 3x por semana',
    'Manter uma alimentação balanceada',
]

# Opções do formulário de interesses do perfil
OBJETIVOS = {
    'emagrecer': 'Emagrecer de forma saudável',
    'ganhar_massa': 'Ganhar massa muscular',
    'manter_peso': 'Manter o peso atual',
    'acompanhar_saude': 'Acompanhar minha saúde',
    'conhecer': 'Apenas conhecer o site',
}

INTERESSES = {
    'imc': 'Calcular meu IMC',
    'gordura': 'Estimar meu percentual de gordura',
    'calorias': 'Calcular meu gasto calórico',
    'metas': 'Acompanhar metas de saúde',
    'dicas': 'Receber recomendações de hábitos saudáveis',
}

FREQUENCIAS = {
    'diaria': 'Todos os dias',
    'semanal': 'Algumas vezes por semana',
    'mensal': 'Uma vez por mês',
    'eventual': 'De vez em quando',
}

# Níveis de atividade física
ATIVIDADES = {
    'sedentario': ('Sedentário (pouco ou nenhum exercício)', 1.2),
    'leve': ('Leve (exercício 1 a 3 dias por semana)', 1.375),
    'moderado': ('Moderado (exercício 3 a 5 dias por semana)', 1.55),
    'intenso': ('Intenso (exercício 6 a 7 dias por semana)', 1.725),
    'muito_intenso': ('Muito intenso (treino pesado ou trabalho físico)', 1.9),
}

# Faixas de gordura
FAIXAS_GORDURA = {
    'masculino': [(6, 'essencial', 'Essencial'), (14, 'atletico', 'Atlético'),
                  (18, 'fitness', 'Fitness'), (25, 'aceitavel', 'Aceitável')],
    'feminino': [(14, 'essencial', 'Essencial'), (21, 'atletico', 'Atlético'),
                 (25, 'fitness', 'Fitness'), (32, 'aceitavel', 'Aceitável')],
}

RECOMENDACOES = {
    'essencial': [
        'Procure orientação de um profissional de saúde para avaliar esse nível de gordura.',
        'Mantenha uma alimentação com energia e nutrientes suficientes para o seu dia a dia.',
    ],
    'atletico': [
        'Mantenha a rotina de treinos e a alimentação equilibrada.',
        'Hidrate-se bem e respeite os dias de descanso.',
    ],
    'fitness': [
        'Continue praticando atividades físicas regularmente.',
        'Priorize frutas, legumes, grãos integrais e boas fontes de proteína.',
    ],
    'aceitavel': [
        'Reduza o consumo de alimentos ultraprocessados e açúcares.',
        'Aumente a frequência de atividades físicas para pelo menos 3x por semana.',
    ],
    'obesidade': [
        'Procure acompanhamento de um médico ou nutricionista.',
        'Comece com atividades leves, como caminhadas diárias, e aumente aos poucos.',
        'Reduza o consumo de alimentos ultraprocessados e açúcares.',
    ],
}


# ---------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------
def num(texto):
    """Converte texto em número (aceita vírgula). Dá ValueError se não for número."""
    valor = float(str(texto).strip().replace(',', '.'))
    if not isfinite(valor):
        raise ValueError('número inválido')
    return valor


def formatar(valor):
    """62.0 vira '62' e 20.67 continua '20.67'."""
    return str(int(valor)) if valor == int(valor) else str(valor)


# ---------------------------------------------------------------
# Validações
# ---------------------------------------------------------------
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validar_conta(nome, email):
    """Valida nome e e-mail. Levanta ValueError com uma mensagem amigável."""
    if not 2 <= len(nome) <= 80:
        raise ValueError('Informe um nome com 2 a 80 caracteres.')
    if len(email) > 120 or not EMAIL_RE.match(email):
        raise ValueError('Informe um e-mail válido.')


def validar_senha(senha):
    """Mínimo de 8 caracteres, com pelo menos uma letra e um número."""
    if not 8 <= len(senha) <= 128:
        raise ValueError('A senha deve ter de 8 a 128 caracteres.')
    if not re.search(r'[A-Za-z]', senha) or not re.search(r'\d', senha):
        raise ValueError('A senha deve ter pelo menos uma letra e um número.')


def tipo_imagem(dados):
    """Descobre o tipo real da imagem pelos primeiros bytes (não confia no nome do arquivo)."""
    if dados.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if dados.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if dados[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if dados[:4] == b'RIFF' and dados[8:12] == b'WEBP':
        return 'webp'
    return None


def ler_foto(arquivo):
    """Valida a foto enviada. Devolve (bytes, extensão) ou (None, None) se não veio arquivo."""
    if arquivo is None or not arquivo.filename:
        return None, None
    dados = arquivo.read(TAMANHO_MAX_UPLOAD + 1)
    if len(dados) > TAMANHO_MAX_UPLOAD:
        raise ValueError('A foto deve ter no máximo 2 MB.')
    extensao = tipo_imagem(dados)
    if extensao is None:
        raise ValueError('Envie uma imagem PNG, JPG, GIF ou WEBP.')
    return dados, extensao


# ---------------------------------------------------------------
# Persistência em data/database.json
# ---------------------------------------------------------------
_trava = threading.RLock()  # impede que dois pedidos gravem o arquivo ao mesmo tempo


def _ler():
    with open(DB_PATH, encoding='utf-8') as arquivo:
        return json.load(arquivo)


def _gravar(usuarios):
    temporario = DB_PATH + '.tmp'
    with open(temporario, 'w', encoding='utf-8') as arquivo:
        json.dump(usuarios, arquivo, ensure_ascii=False, indent=4)
    os.replace(temporario, DB_PATH)  # troca atômica: o arquivo nunca fica pela metade


def _novo_registro(uid, nome, email, senha, funcao, foto):
    return {
        'id': uid,
        'nome': nome,
        'email': email,
        'senha_hash': generate_password_hash(senha, method='pbkdf2:sha256'),
        'foto_perfil': foto,
        'data_cadastro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'funcao': funcao,
        'excluido': False,
    }


def inicializar_banco():
    """Cria o database.json (com um administrador padrão) se ele ainda não existir."""
    if os.path.exists(DB_PATH):
        try:
            if isinstance(_ler(), list):
                return
        except ValueError:
            pass
        # arquivo inválido: guarda uma cópia e recomeça
        os.replace(DB_PATH, DB_PATH + '.corrompido-' + datetime.now().strftime('%Y%m%d%H%M%S'))

    email = os.environ['ADMIN_EMAIL'].strip().lower()
    admin = _novo_registro(1, 'Administrador', email, os.environ['ADMIN_SENHA'], 'admin', AVATAR_PADRAO)
    _gravar([admin])
    print('\n>>> database.json criado com o administrador padrão: %s' % email)
    print('>>> A senha está no arquivo .env (variável ADMIN_SENHA). Troque-a depois de entrar.\n')


def listar_usuarios():
    with _trava:
        return _ler()


def buscar_usuario_por_id(uid):
    return next((u for u in listar_usuarios() if u['id'] == uid), None)


def buscar_usuario_por_email(email):
    email = email.strip().lower()
    return next((u for u in listar_usuarios() if u['email'].lower() == email), None)


def publico(usuario):
    """Cópia do usuário SEM o hash da senha (é a única versão que vai para os templates)."""
    return {chave: valor for chave, valor in usuario.items() if chave != 'senha_hash'}


def _admins_ativos(usuarios, ignorar_id=None):
    return sum(1 for u in usuarios
               if u['funcao'] == 'admin' and not u['excluido'] and u['id'] != ignorar_id)


def _apagar_fotos(uid):
    for nome in os.listdir(UPLOAD_DIR):
        if re.fullmatch(r'usuario_%d\.(png|jpg|gif|webp)' % uid, nome):
            os.remove(os.path.join(UPLOAD_DIR, nome))


def _salvar_foto(dados, extensao, uid):
    _apagar_fotos(uid)  # só existe uma foto por usuário
    nome = 'usuario_%d.%s' % (uid, extensao)
    with open(os.path.join(UPLOAD_DIR, nome), 'wb') as arquivo:
        arquivo.write(dados)
    return 'static/uploads/' + nome


# --- CREATE ---------------------------------------------------
def criar_usuario(nome, email, senha, funcao, arquivo_foto=None):
    dados_foto, extensao = ler_foto(arquivo_foto)
    with _trava:
        usuarios = _ler()
        if any(u['email'].lower() == email for u in usuarios):
            raise ValueError('Este e-mail já está cadastrado.')
        uid = max([u['id'] for u in usuarios], default=0) + 1  # o id nunca se repete
        foto = _salvar_foto(dados_foto, extensao, uid) if dados_foto else AVATAR_PADRAO
        usuario = _novo_registro(uid, nome, email, senha, funcao, foto)
        usuarios.append(usuario)
        _gravar(usuarios)
    return usuario


# --- UPDATE ---------------------------------------------------
def atualizar_usuario(uid, nome, email, nova_senha='', funcao=None, arquivo_foto=None, remover_foto=False):
    dados_foto, extensao = ler_foto(arquivo_foto)
    with _trava:
        usuarios = _ler()
        usuario = next((u for u in usuarios if u['id'] == uid), None)
        if usuario is None:
            raise ValueError('Usuário não encontrado.')
        if any(u['id'] != uid and u['email'].lower() == email for u in usuarios):
            raise ValueError('Este e-mail já está em uso por outra conta.')
        if (funcao and funcao != 'admin' and usuario['funcao'] == 'admin'
                and not usuario['excluido'] and _admins_ativos(usuarios, uid) == 0):
            raise ValueError('O sistema precisa de pelo menos um administrador ativo.')

        usuario['nome'] = nome
        usuario['email'] = email
        if nova_senha:  # senha nova => hash novo, sempre
            usuario['senha_hash'] = generate_password_hash(nova_senha, method='pbkdf2:sha256')
        if funcao:
            usuario['funcao'] = funcao
        if dados_foto:
            usuario['foto_perfil'] = _salvar_foto(dados_foto, extensao, uid)
        elif remover_foto:
            _apagar_fotos(uid)
            usuario['foto_perfil'] = AVATAR_PADRAO
        # data_cadastro e id NUNCA são alterados na edição
        _gravar(usuarios)
        return usuario


def salvar_perfil_saude(uid, dados):
    """Guarda o formulário de interesses dentro do registro do usuário."""
    with _trava:
        usuarios = _ler()
        usuario = next((u for u in usuarios if u['id'] == uid), None)
        if usuario is None:
            raise ValueError('Usuário não encontrado.')
        usuario['perfil_saude'] = dados
        _gravar(usuarios)


# --- DELETE (exclusão lógica / soft delete) -------------------
def definir_exclusao(uid, excluido):
    """Marca a conta como excluída (ou a reativa). O registro continua no arquivo."""
    with _trava:
        usuarios = _ler()
        usuario = next((u for u in usuarios if u['id'] == uid), None)
        if usuario is None:
            raise ValueError('Usuário não encontrado.')
        if (excluido and usuario['funcao'] == 'admin' and not usuario['excluido']
                and _admins_ativos(usuarios, uid) == 0):
            raise ValueError('Não é possível excluir o último administrador ativo.')
        usuario['excluido'] = excluido
        _gravar(usuarios)


garantir_recursos()
inicializar_banco()
# hash "de mentira" usado para o login demorar o mesmo tempo com e-mails que não existem
HASH_FALSO = generate_password_hash(secrets.token_hex(8), method='pbkdf2:sha256')


def calcular_calorias(args):
    """Gasto calórico pela fórmula de Mifflin-St Jeor. Devolve (campos do formulário, resultado)."""
    campos = {
        'sexo': args.get('cal_sexo', 'masculino'),
        'idade': args.get('cal_idade', '').strip(),
        'peso': args.get('cal_peso', '').strip(),
        'altura': args.get('cal_altura', '').strip(),
        'atividade': args.get('cal_atividade', 'sedentario'),
    }
    if campos['sexo'] not in ('masculino', 'feminino'):
        campos['sexo'] = 'masculino'
    if campos['atividade'] not in ATIVIDADES:
        campos['atividade'] = 'sedentario'

    try:
        idade = int(num(campos['idade']))
        peso = num(campos['peso'])
        altura = num(campos['altura'])
    except ValueError:
        return campos, {'erro': 'Preencha idade, peso e altura com números.'}

    if altura > 3:  # altura informada em centímetros
        altura = altura / 100

    if not 15 <= idade <= 120:
        return campos, {'erro': 'A idade deve estar entre 15 e 120 anos.'}
    if not 20 <= peso <= 500:
        return campos, {'erro': 'O peso deve estar entre 20 e 500 kg.'}
    if not 0.5 <= altura <= 2.8:
        return campos, {'erro': 'A altura deve ser informada em metros (ex.: 1,75).'}

    # TMB = 10 x peso(kg) + 6,25 x altura(cm) - 5 x idade + 5 (homens) ou - 161 (mulheres)
    ajuste = 5 if campos['sexo'] == 'masculino' else -161
    tmb = 10 * peso + 6.25 * (altura * 100) - 5 * idade + ajuste
    if tmb <= 0:
        return campos, {'erro': 'Os valores informados não são compatíveis. Confira os dados.'}

    descricao, fator = ATIVIDADES[campos['atividade']]
    gasto_total = tmb * fator

    return campos, {
        'erro': None,
        'tmb': round(tmb),
        'gasto_total': round(gasto_total),
        'atividade': descricao,
        'fator': fator,
        'emagrecer': round(max(gasto_total - 500, tmb)),  # nunca abaixo do gasto em repouso
        'ganhar': round(gasto_total + 300),
    }


def ler_perfil(form):
    """Lê e valida o formulário de interesses do perfil. Devolve (dados, erro)."""
    dados = {
        'idade': '',
        'peso': '',
        'altura': '',
        'sexo': form.get('sexo', '') if form.get('sexo', '') in SEXOS else '',
        'objetivo': form.get('objetivo', '') if form.get('objetivo', '') in OBJETIVOS else '',
        'frequencia': form.get('frequencia', '') if form.get('frequencia', '') in FREQUENCIAS else '',
        'interesses': [i for i in form.getlist('interesses') if i in INTERESSES],
        'observacoes': form.get('observacoes', '').strip()[:300],
    }

    idade_txt = form.get('idade', '').strip()
    peso_txt = form.get('peso', '').strip()
    altura_txt = form.get('altura', '').strip()

    try:
        if idade_txt:
            idade = int(num(idade_txt))
            if not 1 <= idade <= 120:
                return dados, 'A idade deve estar entre 1 e 120 anos.'
            dados['idade'] = str(idade)

        if peso_txt:
            peso = num(peso_txt)
            if not 0 < peso <= 500:
                return dados, 'O peso deve estar entre 1 e 500 kg.'
            dados['peso'] = formatar(peso)

        if altura_txt:
            altura = num(altura_txt)
            if altura > 3:  # altura informada em centímetros
                altura = altura / 100
            if not 0.5 <= altura <= 2.8:
                return dados, 'A altura deve ser informada em metros (ex.: 1,75).'
            dados['altura'] = formatar(round(altura, 2))
    except ValueError:
        return dados, 'Idade, peso e altura precisam ser números.'

    return dados, None


# ---------------------------------------------------------------
# Auxiliares dos templates
# ---------------------------------------------------------------
@app.context_processor
def injetar_ano():
    return {'ano': datetime.now().year}


@app.context_processor
def injetar_usuario():
    return {
        'usuario_logado': 'user_id' in session,
        'usuario_admin': session.get('funcao') == 'admin',
    }


@app.template_global()
def foto_url(usuario):
    """Endereço da foto do usuário (ou do avatar padrão), com a data do arquivo para evitar cache velho."""
    caminho = usuario.get('foto_perfil') or AVATAR_PADRAO
    arquivo = os.path.join(BASE_DIR, caminho)
    if not caminho.startswith('static/') or not os.path.isfile(arquivo):
        caminho = AVATAR_PADRAO
        arquivo = os.path.join(BASE_DIR, caminho)
    versao = int(os.path.getmtime(arquivo)) if os.path.isfile(arquivo) else 0
    return url_for('static', filename=caminho[len('static/'):], v=versao)


@app.template_filter('data_br')
def data_br(texto):
    """'2026-11-13 11:24:00' vira '13/11/2026 às 11:24'."""
    try:
        return datetime.strptime(texto, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y às %H:%M')
    except (TypeError, ValueError):
        return texto or ''


def admin_no_cadastro():
    return os.environ.get('PERMITIR_ADMIN_NO_CADASTRO', '1').strip().lower() in ('1', 'true', 'sim')


# ---------------------------------------------------------------
# Controle de acesso: @login_required e @admin_required
# ---------------------------------------------------------------
def usuario_atual():
    """Usuário da sessão, lido do database.json. Devolve None se não existir ou estiver excluído."""
    uid = session.get('user_id')
    if uid is None:
        return None
    usuario = buscar_usuario_por_id(uid)
    if usuario is None or usuario['excluido']:
        return None
    return usuario


def login_required(funcao):
    @wraps(funcao)
    def protegida(*args, **kwargs):
        usuario = usuario_atual()
        if usuario is None:
            session.clear()
            abort(401)  # não autenticado
        # mantém a sessão igual ao banco (se um admin mudou o e-mail ou a função)
        session['email'] = usuario['email']
        session['funcao'] = usuario['funcao']
        g.usuario = usuario
        return funcao(*args, **kwargs)
    return protegida


def admin_required(funcao):
    @login_required
    @wraps(funcao)
    def protegida(*args, **kwargs):
        if session.get('funcao') != 'admin':
            abort(403)  # autenticado, mas sem permissão
        return funcao(*args, **kwargs)
    return protegida


def pagina_erro(codigo, tipo, titulo, subtitulo, mensagem, botao_texto, botao_url):
    return render_template('erro.html', codigo=codigo, tipo=tipo, titulo=titulo, subtitulo=subtitulo,
                           mensagem=mensagem, botao_texto=botao_texto, botao_url=botao_url), codigo


@app.errorhandler(401)
def erro_401(erro):
    return pagina_erro(401, 'bloqueio', 'Não autorizado', 'Acesso restrito',
                       'Você precisa estar logado para acessar esta página. Por favor, autentique-se para continuar.',
                       'Ir para o Login', url_for('login'))


@app.errorhandler(403)
def erro_403(erro):
    return pagina_erro(403, 'escudo', 'Proibido', 'Acesso restrito a administradores',
                       'Sua conta não possui permissão de administrador para acessar esta área.',
                       'Voltar para o Início', url_for('index'))


@app.errorhandler(404)
def erro_404(erro):
    return pagina_erro(404, 'aviso', 'Página não encontrada', 'Esse endereço não existe',
                       'Confira o endereço digitado ou volte para a página inicial.',
                       'Voltar para o Início', url_for('index'))


@app.errorhandler(413)
def erro_413(erro):
    return pagina_erro(413, 'aviso', 'Arquivo muito grande', 'O envio passou do limite',
                       'A foto deve ter no máximo 2 MB. Escolha uma imagem menor e tente de novo.',
                       'Voltar para o Início', url_for('index'))


# ---------------------------------------------------------------
# Páginas simples
# ---------------------------------------------------------------
@app.route('/')
def index():
    calorias = None
    campos_cal = {'sexo': 'masculino', 'idade': '', 'peso': '', 'altura': '', 'atividade': 'sedentario'}
    if 'cal_peso' in request.args:  # o formulário de calorias foi enviado
        campos_cal, calorias = calcular_calorias(request.args)
    return render_template('index.html', equipe=EQUIPE, calorias=calorias,
                           cal=campos_cal, atividades=ATIVIDADES)


@app.route('/about')
def about():
    # A página "Sobre" agora faz parte da tela inicial
    return redirect(url_for('index') + '#sobre')


# ---------------------------------------------------------------
# Login e logout
# ---------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if usuario_atual():
        return redirect(url_for('index'))

    email, erro = '', None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        usuario = buscar_usuario_por_email(email)

        # confere a senha mesmo se o e-mail não existir (o tempo de resposta é o mesmo)
        senha_correta = check_password_hash(usuario['senha_hash'] if usuario else HASH_FALSO, senha)

        if usuario and senha_correta and not usuario['excluido']:
            session.clear()  # começa uma sessão nova
            session['user_id'] = usuario['id']
            session['email'] = usuario['email']
            session['funcao'] = usuario['funcao']
            return redirect(url_for('index'))
        if usuario and senha_correta and usuario['excluido']:
            erro = 'Esta conta foi desativada e não pode mais entrar.'
        else:
            erro = 'E-mail ou senha incorretos.'
    return render_template('login.html', email=email, erro=erro)


@app.route('/logout')
def logout():
    session.clear()  # fecha o ciclo da sessão
    return redirect(url_for('index'))


# ---------------------------------------------------------------
# Cadastro (Create)
# ---------------------------------------------------------------
def processar_cadastro(permitir_admin):
    """Valida o formulário de cadastro e cria o usuário. Devolve (campos, erro, usuario)."""
    campos = {
        'nome': request.form.get('nome', '').strip(),
        'email': request.form.get('email', '').strip().lower(),
        'funcao': request.form.get('funcao', 'comum'),
    }
    if campos['funcao'] not in FUNCOES or (campos['funcao'] == 'admin' and not permitir_admin):
        campos['funcao'] = 'comum'

    senha = request.form.get('senha', '')
    try:
        validar_conta(campos['nome'], campos['email'])
        validar_senha(senha)
        if senha != request.form.get('confirmar_senha', ''):
            raise ValueError('As senhas não conferem.')
        usuario = criar_usuario(campos['nome'], campos['email'], senha, campos['funcao'],
                                request.files.get('foto'))
    except ValueError as erro:
        return campos, str(erro), None
    return campos, None, usuario


@app.route('/register', methods=['GET', 'POST'])
def register():
    if usuario_atual():
        return redirect(url_for('index'))

    campos, erro = {'nome': '', 'email': '', 'funcao': 'comum'}, None
    if request.method == 'POST':
        campos, erro, usuario = processar_cadastro(admin_no_cadastro())
        if usuario:
            flash('Conta criada com sucesso! Entre com o seu e-mail e a senha.', 'ok')
            return redirect(url_for('login'))
    return render_template('register.html', campos=campos, erro=erro, funcoes=FUNCOES,
                           mostrar_funcao=admin_no_cadastro(), modo_admin=False)


# ---------------------------------------------------------------
# Perfil (Read) e formulário de interesses
# ---------------------------------------------------------------
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    usuario = g.usuario
    perfil = usuario.get('perfil_saude', {})
    erro = None

    if request.method == 'POST':
        dados, erro = ler_perfil(request.form)
        if erro is None:
            salvar_perfil_saude(usuario['id'], dados)
            flash('Perfil atualizado com sucesso!', 'ok')
            return redirect(url_for('profile'))
        perfil = dados  # mantém o que a pessoa digitou para ela corrigir

    return render_template(
        'profile.html',
        usuario=publico(usuario),  # nunca envia o senha_hash
        perfil=perfil,
        preenchido=bool(usuario.get('perfil_saude')),
        erro=erro,
        funcoes=FUNCOES,
        metas=METAS,
        objetivos=OBJETIVOS,
        interesses=INTERESSES,
        frequencias=FREQUENCIAS,
        sexos=SEXOS,
    )


# ---------------------------------------------------------------
# Edição (Update) e exclusão lógica (Delete) da própria conta
# ---------------------------------------------------------------
def tela_edicao(alvo, por_admin):
    """Usada tanto na edição da própria conta quanto na edição feita por um administrador."""
    erro = None
    campos = {'nome': alvo['nome'], 'email': alvo['email'], 'funcao': alvo['funcao']}

    if request.method == 'POST':
        campos['nome'] = request.form.get('nome', '').strip()
        campos['email'] = request.form.get('email', '').strip().lower()
        nova_senha = request.form.get('nova_senha', '')
        funcao = None
        if por_admin and request.form.get('funcao') in FUNCOES:  # só o admin muda a função
            funcao = request.form['funcao']
            campos['funcao'] = funcao
        try:
            validar_conta(campos['nome'], campos['email'])
            if nova_senha:
                validar_senha(nova_senha)
                if nova_senha != request.form.get('confirmar_senha', ''):
                    raise ValueError('As senhas não conferem.')
            atualizar_usuario(alvo['id'], campos['nome'], campos['email'], nova_senha, funcao,
                              request.files.get('foto'), bool(request.form.get('remover_foto')))
        except ValueError as e:
            erro = str(e)
        else:
            flash('Dados atualizados com sucesso!', 'ok')
            return redirect(url_for('admin_dashboard') if por_admin else url_for('profile'))

    return render_template('editar_usuario.html', alvo=publico(alvo), campos=campos, erro=erro,
                           funcoes=FUNCOES, por_admin=por_admin)


@app.route('/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario():
    return tela_edicao(g.usuario, por_admin=False)


@app.route('/excluir-conta', methods=['POST'])
@login_required
def excluir_conta():
    try:
        definir_exclusao(g.usuario['id'], True)  # soft delete: excluido = true
    except ValueError as e:
        flash(str(e), 'erro')
        return redirect(url_for('editar_usuario'))
    session.clear()  # encerra a sessão: a pessoa não consegue mais entrar
    flash('Sua conta foi excluída. Ela não poderá mais ser usada para entrar.', 'ok')
    return redirect(url_for('login'))


# ---------------------------------------------------------------
# Painel administrativo
# ---------------------------------------------------------------
@app.route('/admin')
@admin_required
def admin_dashboard():
    usuarios = sorted(listar_usuarios(), key=lambda u: u['id'])
    hoje = datetime.now().strftime('%Y-%m-%d')
    ativos = [u for u in usuarios if not u['excluido']]
    estatisticas = {
        'total': len(usuarios),
        'ativos': len(ativos),
        'excluidos': len(usuarios) - len(ativos),
        'admins': sum(1 for u in ativos if u['funcao'] == 'admin'),
        'comuns': sum(1 for u in ativos if u['funcao'] == 'comum'),
        'hoje': sum(1 for u in usuarios if u['data_cadastro'].startswith(hoje)),
    }
    return render_template('admin_dashboard.html', usuarios=[publico(u) for u in usuarios],
                           estatisticas=estatisticas, funcoes=FUNCOES)


@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@admin_required
def admin_novo_usuario():
    campos, erro = {'nome': '', 'email': '', 'funcao': 'comum'}, None
    if request.method == 'POST':
        campos, erro, usuario = processar_cadastro(permitir_admin=True)
        if usuario:
            flash('Usuário %s criado com sucesso.' % usuario['nome'], 'ok')
            return redirect(url_for('admin_dashboard'))
    return render_template('register.html', campos=campos, erro=erro, funcoes=FUNCOES,
                           mostrar_funcao=True, modo_admin=True)


@app.route('/admin/usuarios/<int:uid>/editar', methods=['GET', 'POST'])
@admin_required
def admin_editar_usuario(uid):
    alvo = buscar_usuario_por_id(uid)
    if alvo is None:
        abort(404)
    return tela_edicao(alvo, por_admin=True)


@app.route('/admin/usuarios/<int:uid>/excluir', methods=['POST'])
@admin_required
def admin_excluir_usuario(uid):
    try:
        definir_exclusao(uid, True)
    except ValueError as e:
        flash(str(e), 'erro')
        return redirect(url_for('admin_dashboard'))
    if uid == session.get('user_id'):  # o admin excluiu a si mesmo
        session.clear()
        flash('Sua conta foi excluída.', 'ok')
        return redirect(url_for('login'))
    flash('Usuário excluído (exclusão lógica). Você pode reativá-lo quando quiser.', 'ok')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/usuarios/<int:uid>/reativar', methods=['POST'])
@admin_required
def admin_reativar_usuario(uid):
    try:
        definir_exclusao(uid, False)
    except ValueError as e:
        flash(str(e), 'erro')
    else:
        flash('Usuário reativado com sucesso.', 'ok')
    return redirect(url_for('admin_dashboard'))


# ---------------------------------------------------------------
# Calculadora de IMC
# ---------------------------------------------------------------
@app.route('/calcular-imc')
def imc_form():
    """Recebe o formulário e redireciona para /imc/<peso>/<altura>."""
    peso = request.args.get('peso', '').replace(',', '.')
    altura = request.args.get('altura', '').replace(',', '.')
    sexo = request.args.get('sexo', 'outro')
    idade = request.args.get('idade', '25') or '25'
    try:
        num(peso)
        num(altura)
        num(idade)
    except ValueError:
        return redirect(url_for('index'))
    return redirect(url_for('imc', peso=peso, altura=altura, sexo=sexo, idade=idade))


@app.route('/imc/<peso>/<altura>')
def imc(peso, altura):
    sexo = request.args.get('sexo', 'outro').lower()
    if sexo not in SEXOS:
        sexo = 'outro'

    try:
        p = num(peso)
        h = num(altura)
        idade = int(num(request.args.get('idade', '25')))
    except ValueError:
        return render_template('imc.html', erro='Peso, altura e idade precisam ser números.')

    if h > 3:  # altura informada em centímetros (ex.: 175)
        h = h / 100

    if not (0 < p <= 500) or not (0.5 <= h <= 2.8) or not (1 <= idade <= 120):
        return render_template(
            'imc.html',
            erro='Valores fora do limite. Informe peso em kg, altura em metros (ex.: 1,75) e idade entre 1 e 120.',
        )

    # IMC = peso / altura²
    valor_imc = p / (h ** 2)
    if valor_imc < 18.5:
        imc_classe, imc_rotulo = 'magreza', 'Magreza'
    elif valor_imc < 25:
        imc_classe, imc_rotulo = 'normal', 'Normal'
    elif valor_imc < 30:
        imc_classe, imc_rotulo = 'sobrepeso', 'Sobrepeso'
    else:
        imc_classe, imc_rotulo = 'obesidade', 'Obesidade'

    # Peso ideal (IMC 22) e limites da régua (IMC 18,5 / 25 / 30)
    peso_ideal = 22 * h ** 2
    lim1, lim2, lim3 = 18.5 * h ** 2, 25 * h ** 2, 30 * h ** 2

    # Posição do marcador: a régua vai de IMC 15 a IMC 35
    posicao = round(min(max((valor_imc - 15) / 20 * 100, 0), 100), 1)

    # Deurenberg: sexo = 1 (homens) ou 0 (mulheres e outro)
    fator_sexo = 1 if sexo == 'masculino' else 0
    gordura = max(1.20 * valor_imc + 0.23 * idade - 10.8 * fator_sexo - 5.4, 0)

    g_classe, g_rotulo = 'obesidade', 'Obesidade'
    for limite, classe, rotulo in FAIXAS_GORDURA['masculino' if sexo == 'masculino' else 'feminino']:
        if gordura < limite:
            g_classe, g_rotulo = classe, rotulo
            break

    return render_template(
        'imc.html',
        erro=None,
        peso_txt=formatar(p),
        altura_cm=round(h * 100),
        altura_valor=formatar(round(h, 2)),
        sexo=sexo,
        sexo_label=SEXOS[sexo],
        idade=idade,
        imc=valor_imc,
        imc_classe=imc_classe,
        imc_rotulo=imc_rotulo,
        peso_ideal=peso_ideal,
        lim1=lim1,
        lim2=lim2,
        lim3=lim3,
        posicao=posicao,
        gordura=gordura,
        g_classe=g_classe,
        g_rotulo=g_rotulo,
        recomendacoes=RECOMENDACOES[g_classe],
    )


if __name__ == '__main__':
    app.run(debug=True)