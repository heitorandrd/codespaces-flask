from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/calculadora')
def calculadora():
    return render_template('calculadora.html')


@app.route('/resultado', methods=['POST'])
def resultado():
    peso_texto = request.form.get('peso', '')
    calorias_texto = request.form.get('calorias_100g', '')

    try:
        peso = float(peso_texto)
        calorias_100g = float(calorias_texto)
    except ValueError:
        return redirect(url_for('erro_calculo'))

    if peso <= 0 or calorias_100g <= 0:
        return redirect(url_for('erro_calculo'))

    calorias_totais = round((peso * calorias_100g) / 100, 2)

    return render_template(
        'resultado.html',
        peso=peso,
        calorias_100g=calorias_100g,
        calorias_totais=calorias_totais
    )


@app.route('/erro')
def erro_calculo():
    return render_template('erro.html')


@app.route('/perfil')
def perfil():
    return render_template('perfil.html')


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('rastreamento.ico')


if __name__ == '__main__':
    app.run(debug=True)