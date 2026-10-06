from datetime import datetime
from math import isfinite

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)

# ---------------------------------------------------------------
# Dados fixos
# ---------------------------------------------------------------
OPERACOES = {
    'soma': ('Soma', '+'),
    'subtracao': ('Subtração', '-'),
    'multiplicacao': ('Multiplicação', '×'),
    'divisao': ('Divisão', '÷'),
}

SEXOS = {'masculino': 'Masculino', 'feminino': 'Feminino', 'outro': 'Outro'}

EQUIPE = [
    {'nome': 'Diego', 'papel': 'Aluno'},
    {'nome': 'Gustavo', 'papel': 'Aluno'},
    {'nome': 'Heitor', 'papel': 'Aluno'},
]

METAS = [
    'Calcular o IMC mensalmente',
    'Praticar atividade física 3x por semana',
    'Manter uma alimentação balanceada',
]

# Faixas de gordura: (limite superior, classe CSS, nome)
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


@app.context_processor
def injetar_ano():
    return {'ano': datetime.now().year}


# ---------------------------------------------------------------
# Páginas simples
# ---------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html', equipe=EQUIPE)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        if usuario:
            # A senha NÃO vai na URL
            return redirect(url_for('profile', nome=usuario, email=usuario))
    return render_template('login.html')


@app.route('/profile')
def profile():
    nome = request.args.get('nome', 'Visitante')
    return render_template(
        'profile.html',
        nome=nome,
        email=request.args.get('email', 'visitante@exemplo.com'),
        idade=request.args.get('idade', '25'),
        peso=request.args.get('peso', '70.5'),
        altura=request.args.get('altura', '1.75'),
        inicial=nome[0].upper(),
        metas=METAS,
    )


# ---------------------------------------------------------------
# Operações matemáticas
# ---------------------------------------------------------------
@app.route('/calcular-math')
def math_form():
    """Recebe o formulário da página inicial e redireciona para /math/<op>/<a>/<b>."""
    op = request.args.get('operacao', 'soma')
    a = request.args.get('primeiro', '').replace(',', '.')
    b = request.args.get('segundo', '').replace(',', '.')
    try:
        num(a)
        num(b)
    except ValueError:
        return redirect(url_for('index'))
    return redirect(url_for('math_result', op=op, a=a, b=b))


@app.route('/math/<op>/<a>/<b>')
def math_result(op, a, b):
    nome, simbolo = OPERACOES.get(op, ('Inválida', None))

    try:
        x = num(a)
        y = num(b)
    except ValueError:
        return render_template('math.html', op_nome=nome, simbolo=None, a=a, b=b,
                               resultado=None, erro='Os valores precisam ser números.')

    if simbolo is None:
        return render_template('math.html', op_nome=nome, simbolo=None, a=a, b=b,
                               resultado=None, erro='Operação inválida.')

    if op == 'divisao' and y == 0:
        return render_template('math.html', op_nome=nome, simbolo=simbolo,
                               a=formatar(x), b=formatar(y), resultado=None,
                               erro='Não é possível dividir por zero.')

    if op == 'soma':
        valor = x + y
    elif op == 'subtracao':
        valor = x - y
    elif op == 'multiplicacao':
        valor = x * y
    else:
        valor = x / y

    return render_template('math.html', op_nome=nome, simbolo=simbolo,
                           a=formatar(x), b=formatar(y),
                           resultado=formatar(round(valor, 2)), erro=None)


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