// Aplica imediatamente ao carregar para evitar "piscar" de tela branca
(function() {
    if (localStorage.getItem('tema_contraste') === 'alto') {
        document.body.classList.add('alto-contraste');
    }
})();

function alternarContraste() {
    const corpo = document.body;
    corpo.classList.toggle('alto-contraste');

    if (corpo.classList.contains('alto-contraste')) {
        localStorage.setItem('tema_contraste', 'alto');
    } else {
        localStorage.setItem('tema_contraste', 'padrao');
    }
}