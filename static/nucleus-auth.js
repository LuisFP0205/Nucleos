/**
 * Nucleus Auth — utilitário compartilhado de autenticação via Supabase.
 * Requer: @supabase/supabase-js carregado antes deste script.
 */
const NucleusAuth = (() => {
  let _sb = null;
  const TS_KEY   = 'nucleus_login_ts';
  const MAX_DAYS = 120;
  const TIMEOUT_MS = 6000; // se o guard travar, mostra a página após 6s

  // Segurança: mostra a página automaticamente se o guard demorar demais
  let _showTimer = null;

  function _show() {
    if (_showTimer) { clearTimeout(_showTimer); _showTimer = null; }
    document.getElementById('_ah')?.remove();
  }

  function _armTimeout() {
    _showTimer = setTimeout(() => {
      console.warn('[NucleusAuth] Timeout — mostrando página');
      _show();
    }, TIMEOUT_MS);
  }

  async function _client() {
    if (_sb) return _sb;
    // Verifica se o CDN do Supabase carregou
    if (typeof supabase === 'undefined') return null;
    const res = await fetch('/auth/supabase/config');
    if (!res.ok) throw new Error('config unavailable');
    const cfg = await res.json();
    if (!cfg.enabled) return null;
    _sb = supabase.createClient(cfg.url, cfg.anon_key);
    window._sb = _sb;
    return _sb;
  }

  /** Verifica sessão. Redireciona para /login se não autenticado. */
  async function guard() {
    _armTimeout();
    try {
      const sb = await _client();
      if (!sb) { _show(); return true; } // Supabase não configurado → acesso livre

      const { data: { session } } = await sb.auth.getSession();
      if (!session) { _show(); location.replace('/login'); return false; }

      const ts = localStorage.getItem(TS_KEY);
      if (!ts) {
        localStorage.setItem(TS_KEY, Date.now().toString());
      } else if (Date.now() - parseInt(ts) > MAX_DAYS * 86400 * 1000) {
        await sb.auth.signOut();
        localStorage.removeItem(TS_KEY);
        _show();
        location.replace('/login?expired=1');
        return false;
      }

      window._session = session;
      _show();
      return true;
    } catch (e) {
      console.warn('[NucleusAuth] Erro no guard:', e);
      _show(); // nunca bloqueia o app em caso de erro
      return true;
    }
  }

  /** Retorna o perfil completo do usuário. */
  async function profile() {
    try {
      const sb = await _client();
      if (!sb) return null;
      const { data } = await sb.from('profiles').select(
        'is_premium, premium_until, username, ' +
        'twitch_channel, youtube_channel_id, kick_channel, ' +
        'chat_twitch, chat_youtube, chat_kick, ' +
        'chat_timeout, chat_max_messages, viewers_positions, overlay_themes'
      ).single();
      // Expiração: se premium_until passou, dispara UPDATE para o trigger do banco
      // O trigger check_premium_expiry() zera is_premium e premium_until automaticamente
      if (data && data.is_premium && data.premium_until) {
        if (new Date(data.premium_until) < new Date()) {
          data.is_premium    = false;  // atualiza localmente para UX imediata
          data.premium_until = null;
          // UPDATE aciona o trigger — ele confirma a expiração no banco
          saveSettings({ premium_until: null }).catch(() => {});
        }
      }
      return data;
    } catch { return null; }
  }

  /** Salva campos parciais no perfil do usuário. */
  async function saveSettings(data) {
    try {
      const sb = await _client();
      if (!sb) {
        console.warn('[NucleusAuth] saveSettings: cliente Supabase não disponível');
        return false;
      }
      const { data: { user }, error: userError } = await sb.auth.getUser();
      if (userError) {
        console.error('[NucleusAuth] saveSettings: erro ao obter usuário:', userError.message);
        return false;
      }
      if (!user) {
        console.warn('[NucleusAuth] saveSettings: nenhum usuário logado');
        return false;
      }
      console.log('[NucleusAuth] saveSettings: salvando para user', user.id, data);
      const { error } = await sb.from('profiles').update(data).eq('id', user.id);
      if (error) {
        console.error('[NucleusAuth] saveSettings: erro do Supabase:', error.message, error);
        return false;
      }
      console.log('[NucleusAuth] saveSettings: salvo com sucesso');
      return true;
    } catch (e) {
      console.error('[NucleusAuth] saveSettings: exceção:', e);
      return false;
    }
  }

  /** Retorna o usuário da sessão atual, ou null. */
  async function currentUser() {
    try {
      const sb = await _client();
      if (!sb) return null;
      const { data: { user } } = await sb.auth.getUser();
      return user;
    } catch { return null; }
  }

  /** Faz logout e redireciona para /login. */
  async function signOut() {
    try {
      const sb = await _client();
      if (sb) await sb.auth.signOut();
    } catch {}
    localStorage.removeItem(TS_KEY);
    location.replace('/login');
  }

  return { guard, profile, saveSettings, currentUser, signOut };
})();
