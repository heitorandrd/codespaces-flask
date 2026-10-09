import os
from datetime import datetime
from math import isfinite

from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
# guardar o login na sessão.
app.secret_key = os.environ.get('SECRET_KEY', 'troque-esta-chave-em-producao')

# Dados fixos
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

# Opções do formulári
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


# Funções auxiliares
def num(texto):
    """Converte texto em número (aceita vírgula). Dá ValueError se não for número."""
    valor = float(str(texto).strip().replace(',', '.'))
    if not isfinite(valor):
        raise ValueError('número inválido')
    return valor


def formatar(valor):
    """62.0 vira '62' e 20.67 continua '20.67'."""
    return str(int(valor)) if valor == int(valor) else str(valor)


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


def ler_perfil(form, usuario):
    """Lê e valida o formulário do perfil. Devolve (dados, erro)."""
    dados = {
        'nome': form.get('nome', '').strip()[:60] or usuario['nome'],
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


@app.context_processor
def injetar_ano():
    return {'ano': datetime.now().year}


@app.context_processor
def injetar_usuario():
    return {'usuario_logado': 'usuario' in session}


# Páginas simples
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
    # "Sobre" JUNTA CM da tela inicial
    return redirect(url_for('index') + '#sobre')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        if usuario:
            # A senha NÃO é guardada.
            session.clear()
            session['usuario'] = {'nome': usuario, 'email': usuario}
            return redirect(url_for('profile'))
    elif 'usuario' in session:
        return redirect(url_for('profile'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()  # login e perfil deixam de existir
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    usuario = session.get('usuario')
    if not usuario:
        return redirect(url_for('login'))

    perfil = session.get('perfil', {})
    erro = None

    if request.method == 'POST':
        dados, erro = ler_perfil(request.form, usuario)
        if erro is None:
            session['perfil'] = dados
            flash('Perfil atualizado com sucesso!')
            return redirect(url_for('profile'))
        perfil = dados  # mantém o que a pessoa digito

    nome = perfil.get('nome') or usuario['nome']
    return render_template(
        'profile.html',
        nome=nome,
        email=usuario['email'],
        inicial=nome[0].upper(),
        perfil=perfil,
        preenchido='perfil' in session,
        erro=erro,
        metas=METAS,
        objetivos=OBJETIVOS,
        interesses=INTERESSES,
        frequencias=FREQUENCIAS,
        sexos=SEXOS,
    )


# Calculadora de IMC

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