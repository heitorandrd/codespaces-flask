/* Validações de interface das telas de login, cadastro, edição e painel admin.
   O script é carregado em todas as páginas (base.html) e só age onde encontra os elementos. */
(function () {
  'use strict';

  var TIPOS_FOTO = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  var TAMANHO_MAX_FOTO = 2 * 1024 * 1024; // 2 MB, o mesmo limite do servidor

  function mostrarMensagem(id, texto, tipo) {
    var alvo = document.querySelector('[data-msg-de="' + id + '"]');
    if (!alvo) { return; }
    alvo.textContent = texto;
    alvo.classList.toggle('erro', tipo === 'erro');
    alvo.classList.toggle('ok', tipo === 'ok');
  }

  /* 1. Botão de "olho": alterna entre mostrar e ocultar a senha */
  function iniciarOlhos() {
    document.querySelectorAll('.toggle-senha').forEach(function (botao) {
      botao.addEventListener('click', function () {
        var campo = document.getElementById(botao.dataset.alvo);
        var mostrar = campo.type === 'password';
        campo.type = mostrar ? 'text' : 'password';
        botao.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
        botao.setAttribute('aria-label', mostrar ? 'Ocultar senha' : 'Mostrar senha');
        botao.querySelector('.icone-olho').classList.toggle('oculto', mostrar);
        botao.querySelector('.icone-olho-off').classList.toggle('oculto', !mostrar);
        campo.focus();
      });
    });
  }

  /* 2. Aviso de Caps Lock: keydown, keyup e focus (mais mouse, para avisar antes da primeira tecla) */
  function iniciarCapsLock() {
    var avisos = document.querySelectorAll('.caps-aviso');
    if (!avisos.length) { return; }
    var ativo = false;

    function atualizar(evento) {
      // eventos de teclado e de mouse informam o estado do Caps Lock; o "focus" não
      // informa, então nesse caso vale o último estado conhecido
      if (evento && typeof evento.getModifierState === 'function') {
        ativo = evento.getModifierState('CapsLock');
      }
      avisos.forEach(function (aviso) { aviso.hidden = !ativo; });
    }

    ['keydown', 'keyup', 'mousedown', 'mouseup', 'click', 'mousemove'].forEach(function (tipo) {
      document.addEventListener(tipo, atualizar);
    });
    document.querySelectorAll('.campo-senha').forEach(function (campo) {
      campo.addEventListener('focus', atualizar);
    });
  }

  /* 3. Medidor de força da senha */
  function pontuar(senha) {
    var pontos = 0;
    if (senha.length >= 8) { pontos++; }
    if (senha.length >= 12) { pontos++; }
    if (/[a-z]/.test(senha) && /[A-Z]/.test(senha)) { pontos++; }
    if (/\d/.test(senha)) { pontos++; }
    if (/[^A-Za-z0-9]/.test(senha)) { pontos++; }
    return pontos;
  }

  function iniciarForca() {
    document.querySelectorAll('[data-forca]').forEach(function (campo) {
      var medidor = document.getElementById(campo.dataset.forca);
      var barra = medidor.querySelector('.forca-barra');
      var texto = medidor.querySelector('.forca-texto');
      campo.addEventListener('input', function () {
        if (!campo.value) { medidor.hidden = true; return; }
        var pontos = pontuar(campo.value);
        var nivel = pontos <= 2 ? 'fraca' : (pontos <= 3 ? 'media' : 'forte');
        medidor.hidden = false;
        medidor.className = 'forca forca-' + nivel;
        barra.style.width = (pontos / 5 * 100) + '%';
        texto.textContent = 'Senha ' + { fraca: 'fraca', media: 'média', forte: 'forte' }[nivel];
      });
    });
  }

  /* 4. Confirmação de senha: os dois campos precisam ser iguais */
  function iniciarConfirmacao() {
    document.querySelectorAll('[data-confirma]').forEach(function (confirmacao) {
      var principal = document.getElementById(confirmacao.dataset.confirma);

      function verificar() {
        // na edição, a confirmação só é obrigatória quando uma senha nova é digitada
        confirmacao.required = principal.required || principal.value !== '';
        if (!principal.value && !confirmacao.value) {
          confirmacao.setCustomValidity('');
          mostrarMensagem(confirmacao.id, '', '');
          return;
        }
        if (confirmacao.value !== principal.value) {
          confirmacao.setCustomValidity('As senhas não conferem.');
          mostrarMensagem(confirmacao.id, 'As senhas não conferem.', 'erro');
        } else {
          confirmacao.setCustomValidity('');
          mostrarMensagem(confirmacao.id, 'As senhas conferem.', 'ok');
        }
      }

      principal.addEventListener('input', verificar);
      confirmacao.addEventListener('input', verificar);
      verificar();
    });
  }

  /* 5. Foto de perfil: valida tipo, tamanho e conteúdo e mostra a pré-visualização */
  function tipoPelosBytes(bytes) {
    function comeca(lista) { return lista.every(function (valor, i) { return bytes[i] === valor; }); }
    if (comeca([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) { return true; }   // PNG
    if (comeca([0xFF, 0xD8, 0xFF])) { return true; }                                 // JPG
    if (comeca([0x47, 0x49, 0x46, 0x38])) { return true; }                           // GIF
    if (comeca([0x52, 0x49, 0x46, 0x46]) && bytes[8] === 0x57 && bytes[9] === 0x45) { return true; } // WEBP
    return false;
  }

  function iniciarFoto() {
    document.querySelectorAll('input[type="file"][data-preview]').forEach(function (entrada) {
      var previa = document.getElementById(entrada.dataset.preview);
      var original = previa.src;

      function rejeitar(erro) {
        entrada.setCustomValidity(erro);
        entrada.value = '';
        previa.src = original;
        mostrarMensagem(entrada.id, erro, 'erro');
      }

      entrada.addEventListener('change', function () {
        var arquivo = entrada.files[0];
        entrada.setCustomValidity('');
        if (!arquivo) {
          previa.src = original;
          mostrarMensagem(entrada.id, 'PNG, JPG, GIF ou WEBP, até 2 MB.', '');
          return;
        }
        if (TIPOS_FOTO.indexOf(arquivo.type) === -1) {
          rejeitar('Escolha uma imagem PNG, JPG, GIF ou WEBP.');
          return;
        }
        if (arquivo.size > TAMANHO_MAX_FOTO) {
          rejeitar('A foto deve ter no máximo 2 MB.');
          return;
        }
        // confere o conteúdo real do arquivo (o tipo acima vem só da extensão do nome)
        var leitor = new FileReader();
        leitor.onload = function () {
          if (!tipoPelosBytes(new Uint8Array(leitor.result))) {
            rejeitar('Esse arquivo não é uma imagem válida.');
            return;
          }
          previa.src = URL.createObjectURL(arquivo);
          mostrarMensagem(entrada.id, arquivo.name, 'ok');
        };
        leitor.readAsArrayBuffer(arquivo.slice(0, 12));
      });
    });
  }

  /* 6. Pede confirmação antes de enviar formulários perigosos (excluir, reativar) */
  function iniciarConfirmacoes() {
    document.querySelectorAll('form[data-confirmar]').forEach(function (formulario) {
      formulario.addEventListener('submit', function (evento) {
        if (!window.confirm(formulario.dataset.confirmar)) {
          evento.preventDefault();
        }
      });
    });
  }

  /* 7. Painel admin: busca instantânea na tabela de usuários */
  function iniciarBusca() {
    var campo = document.getElementById('busca-usuarios');
    if (!campo) { return; }
    var linhas = document.querySelectorAll('#tabela-usuarios tbody tr');
    var vazio = document.getElementById('busca-vazio');

    campo.addEventListener('input', function () {
      var termo = campo.value.trim().toLowerCase();
      var visiveis = 0;
      linhas.forEach(function (linha) {
        var combina = linha.dataset.busca.toLowerCase().indexOf(termo) !== -1;
        linha.hidden = !combina;
        if (combina) { visiveis++; }
      });
      vazio.hidden = visiveis !== 0;
    });
  }

  iniciarOlhos();
  iniciarCapsLock();
  iniciarForca();
  iniciarConfirmacao();
  iniciarFoto();
  iniciarConfirmacoes();
  iniciarBusca();
})();