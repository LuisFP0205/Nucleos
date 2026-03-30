// theme.js — Gerenciamento de tema claro/escuro compartilhado entre páginas
(function () {
  const STORAGE_KEY = 'nucleus-theme';

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    // Atualiza ícone do botão se existir
    const btn = document.getElementById('theme-btn');
    if (btn) btn.textContent = theme === 'light' ? '🌙' : '☀️';
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Aplica tema salvo imediatamente (evita flash)
  applyTheme(localStorage.getItem(STORAGE_KEY) || 'dark');

  // Expõe globalmente
  window.toggleTheme = toggleTheme;
  window.applyTheme  = applyTheme;
})();
