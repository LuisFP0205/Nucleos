/**
 * Nucleus Sidebar — shared navigation component.
 * Include with: <script src="/static/nucleus-sidebar.js"></script>
 */
(function () {
  "use strict";

  const NAV = [
    { id: "dashboard",   label: "Dashboard",  href: "/" },
    { id: "connections", label: "Conexões",   href: "/connections" },
    { id: "chat",        label: "Chat",        href: "/chat" },
    { id: "commands",    label: "Comandos",    href: "/commands" },
    { id: "overlays",    label: "Overlays",    href: "/overlays" },
    { id: "music",       label: "Música",      href: "/music" },
    { id: "analytics",   label: "Analytics",   href: "/analytics" },
    { id: "settings",    label: "Config",      href: "/settings" },
    { id: "guide",       label: "Guia",        href: "/guide" },
  ];

  const ICONS = {
    dashboard:   `<svg viewBox="0 0 20 20"><rect x="2" y="2" width="7" height="7" rx="1.5"/><rect x="11" y="2" width="7" height="7" rx="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5"/><rect x="11" y="11" width="7" height="7" rx="1.5"/></svg>`,
    connections: `<svg viewBox="0 0 20 20"><circle cx="4" cy="10" r="2.5"/><circle cx="16" cy="5" r="2.5"/><circle cx="16" cy="15" r="2.5"/><line x1="6.2" y1="9" x2="13.8" y2="6"/><line x1="6.2" y1="11" x2="13.8" y2="14"/></svg>`,
    chat:        `<svg viewBox="0 0 20 20"><path d="M3 3h14v10H11l-4 4v-4H3z"/></svg>`,
    commands:    `<svg viewBox="0 0 20 20"><polyline points="4,6 2,10 4,14"/><polyline points="16,6 18,10 16,14"/><line x1="8" y1="4" x2="12" y2="16"/></svg>`,
    overlays:    `<svg viewBox="0 0 20 20"><rect x="2" y="2" width="16" height="11" rx="2"/><rect x="6" y="15" width="8" height="2" rx="1"/><line x1="10" y1="13" x2="10" y2="15"/></svg>`,
    music:       `<svg viewBox="0 0 20 20"><circle cx="5" cy="15" r="2.5"/><circle cx="15" cy="13" r="2.5"/><polyline points="7.5,15 7.5,5 17.5,3 17.5,13"/><line x1="7.5" y1="5" x2="17.5" y2="3"/></svg>`,
    analytics:   `<svg viewBox="0 0 20 20"><rect x="2" y="11" width="4" height="7"/><rect x="8" y="7" width="4" height="11"/><rect x="14" y="3" width="4" height="15"/></svg>`,
    settings:    `<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="3"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M4.2 15.8l1.4-1.4M14.4 5.6l1.4-1.4"/></svg>`,
    guide:       `<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8"/><line x1="10" y1="9" x2="10" y2="14"/><circle cx="10" cy="6.5" r="1"/></svg>`,
  };

  const LS_COL = "nk_sb_col";

  // ─── CSS ──────────────────────────────────────────────────────────────────
  const CSS = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
      --sb-w:   220px;
      --sb-wc:   58px;
      --bg:     #060912;
      --wrap:   #0e1120;
      --card:   #141828;
      --card2:  #1a1f32;
      --border: rgba(255,255,255,0.07);
      --border2:rgba(255,255,255,0.12);
      --text:   #dde3f0;
      --muted:  #4b5478;
      --dim:    #252b42;
      --purple: #9147ff;
      --purple2:#7c3aed;
      --cyan:   #00c8e0;
      --cyan2:  #00a8be;
      --green:  #22c55e;
      --red:    #ef4444;
      --yellow: #eab308;
      --mono:   'JetBrains Mono', 'Fira Code', monospace;
      --r1: 6px; --r2: 8px; --r3: 12px;
      --trans: 0.2s cubic-bezier(.4,0,.2,1);
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    html, body {
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', 'Segoe UI', system-ui, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif;
      font-size: 13px;
      -webkit-font-smoothing: antialiased;
    }

    body:not([data-sb-no-push]) { padding-left: var(--sb-w); transition: padding-left var(--trans); }
    body:not([data-sb-no-push]).sb-col { padding-left: var(--sb-wc); }

    /* ── Sidebar shell ── */
    #nk-sidebar {
      position: fixed; top: 0; left: 0; bottom: 0;
      width: var(--sb-w);
      background: var(--wrap);
      border-right: 1px solid var(--border);
      display: flex; flex-direction: column;
      z-index: 9000;
      transition: width var(--trans);
      overflow: hidden;
    }
    #nk-sidebar.col { width: var(--sb-wc); }

    /* Header */
    .sb-head {
      height: 56px; min-height: 56px;
      display: flex; align-items: center;
      padding: 0 14px; gap: 8px;
      border-bottom: 1px solid var(--border);
      position: relative;
    }
    .sb-logo-mark {
      width: 32px; height: 32px; border-radius: var(--r2); flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      overflow: hidden;
    }
    .sb-logo-mark img { width: 32px; height: 32px; object-fit: contain; }
    .sb-logo-text {
      font-size: 15px; font-weight: 700; color: var(--text);
      white-space: nowrap; letter-spacing: .3px;
      transition: opacity var(--trans), width var(--trans);
    }
    #nk-sidebar.col .sb-logo-text { opacity: 0; pointer-events: none; width: 0; }

    .sb-col-btn {
      width: 22px; height: 22px; border-radius: var(--r1); flex-shrink: 0;
      background: var(--card); border: 1px solid var(--border2);
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      color: var(--muted); font-size: 9px;
      transition: color .15s, background .15s, transform .2s;
      position: absolute; right: -11px; top: 50%; transform: translateY(-50%);
      z-index: 1;
    }
    .sb-col-btn:hover { color: var(--text); background: var(--card2); }
    #nk-sidebar.col .sb-col-btn { transform: translateY(-50%) rotate(180deg); }

    /* Nav */
    .sb-nav { flex: 1; overflow-y: auto; padding: 8px 0; }
    .sb-item {
      display: flex; align-items: center; gap: 10px;
      height: 38px; padding: 0 14px;
      color: var(--muted); font-size: 13px; font-weight: 500;
      cursor: pointer; text-decoration: none;
      transition: color .15s, background .15s;
      position: relative; white-space: nowrap;
      border-radius: 0;
    }
    .sb-item:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    .sb-item.active {
      color: var(--text);
      background: rgba(145,71,255,0.12);
    }
    .sb-item.active::before {
      content: ''; position: absolute;
      left: 0; top: 6px; bottom: 6px; width: 3px;
      background: var(--purple); border-radius: 0 3px 3px 0;
    }
    .sb-icon {
      width: 18px; height: 18px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
    }
    .sb-icon svg {
      width: 16px; height: 16px;
      fill: none; stroke: currentColor; stroke-width: 1.6;
      stroke-linecap: round; stroke-linejoin: round;
    }
    .sb-label { transition: opacity var(--trans); }
    #nk-sidebar.col .sb-label { opacity: 0; pointer-events: none; }

    /* Tooltip when collapsed */
    #nk-sidebar.col .sb-item:hover::after {
      content: attr(data-label);
      position: absolute; left: calc(var(--sb-wc) + 10px); top: 50%;
      transform: translateY(-50%);
      background: var(--card2); border: 1px solid var(--border2);
      color: var(--text); padding: 5px 10px; border-radius: var(--r1);
      font-size: 12px; white-space: nowrap; z-index: 9999;
      box-shadow: 0 4px 16px rgba(0,0,0,.5);
    }

    /* Platforms strip */
    .sb-plats {
      padding: 10px 12px; border-top: 1px solid var(--border);
      display: flex; flex-direction: column; gap: 5px;
    }
    .sb-plat {
      display: flex; align-items: center; gap: 8px;
      font-size: 11.5px; color: var(--muted); height: 22px;
      font-family: var(--mono);
    }
    .sb-pdot {
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--dim); flex-shrink: 0; transition: background .3s;
    }
    .sb-pdot.live { background: var(--green); box-shadow: 0 0 6px var(--green); }
    .sb-pname { transition: opacity var(--trans); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
    #nk-sidebar.col .sb-pname { opacity: 0; }

    /* User */
    .sb-user {
      height: 52px; min-height: 52px; border-top: 1px solid var(--border);
      display: flex; align-items: center; gap: 10px;
      padding: 0 14px; cursor: pointer;
      transition: background .15s; overflow: hidden;
    }
    .sb-user:hover { background: rgba(255,255,255,0.04); }
    .sb-avatar {
      width: 28px; height: 28px; border-radius: var(--r1); flex-shrink: 0;
      background: linear-gradient(135deg, var(--purple2), #1a1040);
      display: flex; align-items: center; justify-content: center;
      font-size: 12px; font-weight: 700; color: #fff; overflow: hidden;
    }
    .sb-avatar img { width: 100%; height: 100%; object-fit: cover; }
    .sb-uinfo { overflow: hidden; transition: opacity var(--trans); }
    #nk-sidebar.col .sb-uinfo { opacity: 0; }
    .sb-uemail { font-size: 11.5px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .sb-uplan  { font-size: 10px; color: var(--muted); margin-top: 1px; font-family: var(--mono); text-transform: uppercase; letter-spacing: .5px; }
    .sb-uplan.premium { color: var(--purple); }

    /* ── Update banner ── */
    .sb-update {
      display: none; margin: 8px 10px; padding: 8px 10px;
      background: rgba(234,179,8,.08); border: 1px solid rgba(234,179,8,.25);
      border-radius: 8px; cursor: pointer; transition: background .15s;
    }
    .sb-update:hover { background: rgba(234,179,8,.14); }
    .sb-update-title { font-size: 11px; font-weight: 700; color: #eab308; margin-bottom: 2px; }
    .sb-update-sub   { font-size: 10.5px; color: var(--muted); }

    /* ── Global shared styles ── */
    .page-wrap {
      min-height: 100vh; display: flex; flex-direction: column;
      background: var(--bg); overflow: hidden;
    }
    .page-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 24px 0; gap: 12px;
    }
    .page-title { font-size: 20px; font-weight: 800; color: var(--text); }
    .page-sub   { font-size: 12px; color: var(--muted); margin-top: 3px; }
    .page-body  { flex: 1; padding: 20px 24px; overflow-y: auto; }

    /* Card */
    .nk-card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--r3); overflow: hidden;
    }
    .nk-card-hd {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 18px; border-bottom: 1px solid var(--border);
      font-size: 11px; font-weight: 700; color: var(--muted);
      text-transform: uppercase; letter-spacing: .7px;
    }
    .nk-card-body { padding: 16px 18px; }

    /* Buttons */
    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      height: 34px; padding: 0 14px;
      font-size: 12.5px; font-weight: 600; font-family: inherit;
      cursor: pointer; border: 1px solid transparent;
      border-radius: var(--r2); white-space: nowrap;
      transition: all .15s; text-decoration: none;
    }
    .btn:active { transform: scale(.97); }
    .btn-sm { height: 28px; padding: 0 10px; font-size: 12px; }
    .btn-primary { background: var(--purple); color: #fff; }
    .btn-primary:hover { background: var(--purple2); }
    .btn-cyan    { background: var(--cyan); color: #000; }
    .btn-cyan:hover { background: var(--cyan2); }
    .btn-ghost   { background: transparent; color: var(--muted); border-color: var(--border2); }
    .btn-ghost:hover { color: var(--text); border-color: rgba(255,255,255,.2); background: rgba(255,255,255,.04); }
    .btn-danger  { background: rgba(239,68,68,.12); color: var(--red); border-color: rgba(239,68,68,.2); }
    .btn-danger:hover { background: rgba(239,68,68,.22); }

    /* Input */
    .nk-input {
      height: 36px; padding: 0 12px; width: 100%;
      background: var(--bg); border: 1px solid var(--border2);
      border-radius: var(--r2); color: var(--text);
      font-size: 13px; font-family: inherit; outline: none;
      transition: border-color .15s;
    }
    .nk-input:focus { border-color: var(--purple); }
    .nk-input::placeholder { color: var(--muted); }
    textarea.nk-input { height: auto; padding: 10px 12px; resize: vertical; }

    /* Toggle */
    .nk-toggle { position: relative; width: 36px; height: 20px; flex-shrink: 0; }
    .nk-toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
    .nk-toggle-track {
      position: absolute; inset: 0; border-radius: 10px;
      background: var(--dim); cursor: pointer; transition: background .2s;
    }
    .nk-toggle-track::before {
      content: ''; position: absolute;
      width: 14px; height: 14px; border-radius: 50%;
      top: 3px; left: 3px; background: var(--muted);
      transition: transform .2s, background .2s;
    }
    .nk-toggle input:checked ~ .nk-toggle-track { background: rgba(0,200,224,.2); }
    .nk-toggle input:checked ~ .nk-toggle-track::before { transform: translateX(16px); background: var(--cyan); }

    /* Badge */
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 20px;
      font-size: 10.5px; font-weight: 700; letter-spacing: .3px;
    }
    .badge-live    { background: rgba(34,197,94,.15);  color: var(--green); border: 1px solid rgba(34,197,94,.25); }
    .badge-offline { background: rgba(30,30,60,.8);    color: var(--dim);   border: 1px solid var(--border); }
    .badge-conn    { background: rgba(34,197,94,.12);  color: var(--green); }
    .badge-disc    { background: var(--dim);            color: var(--muted); }
    .badge-built   { background: rgba(145,71,255,.15); color: var(--purple); border: 1px solid rgba(145,71,255,.2); }
    .badge-custom  { background: rgba(0,200,224,.12);  color: var(--cyan);   border: 1px solid rgba(0,200,224,.2); }
    .badge-err     { background: rgba(239,68,68,.12);  color: var(--red); }
    .badge-warn    { background: rgba(234,179,8,.12);  color: var(--yellow); }

    /* Status dot */
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--dim); flex-shrink: 0; }
    .dot.live { background: var(--green); box-shadow: 0 0 8px var(--green); animation: dotpulse 2s infinite; }
    .dot.err  { background: var(--red); }
    @keyframes dotpulse { 0%,100%{opacity:1} 50%{opacity:.4} }

    /* Row utils */
    .flex { display: flex; align-items: center; }
    .gap4 { gap: 4px; } .gap6 { gap: 6px; } .gap8 { gap: 8px; } .gap12 { gap: 12px; } .gap16 { gap: 16px; }
    .spacer { flex: 1; }
    .mono { font-family: var(--mono); }

    /* Divider */
    .divider { border: none; border-top: 1px solid var(--border); margin: 0; }

    /* Toast */
    #nk-toasts {
      position: fixed; bottom: 20px; right: 20px;
      display: flex; flex-direction: column-reverse; gap: 8px; z-index: 99999;
    }
    .nk-toast {
      background: var(--card2); border: 1px solid var(--border2);
      border-radius: var(--r2); padding: 10px 14px;
      font-size: 13px; color: var(--text); max-width: 280px;
      box-shadow: 0 8px 24px rgba(0,0,0,.5);
      animation: toastin .15s ease;
    }
    .nk-toast.ok    { border-left: 3px solid var(--green); }
    .nk-toast.error { border-left: 3px solid var(--red); }
    .nk-toast.info  { border-left: 3px solid var(--purple); }
    @keyframes toastin { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--muted); }
    * { scrollbar-width: thin; scrollbar-color: var(--border2) transparent; }

    ::selection { background: rgba(145,71,255,.3); }

    /* ── Light mode ── */
    html[data-theme="light"] {
      --bg:      #f0f2fa;
      --wrap:    #ffffff;
      --card:    #f7f8fd;
      --card2:   #eef0f8;
      --border:  rgba(15,25,80,0.08);
      --border2: rgba(15,25,80,0.14);
      --text:    #0d1229;
      --muted:   #5e6d96;
      --dim:     #b8c3df;
    }
    html[data-theme="light"] .btn-ghost {
      background: transparent; color: var(--muted); border-color: var(--border2);
    }
    html[data-theme="light"] .btn-ghost:hover {
      background: var(--card2); color: var(--text);
    }
    html[data-theme="light"] #nk-sidebar { box-shadow: 2px 0 12px rgba(0,0,0,.06); }

    /* ── OBS scene widget ── */
    .sb-obs {
      border-top: 1px solid var(--border);
      padding: 8px 12px;
      position: relative;
    }
    .sb-obs-row {
      display: flex; align-items: center; gap: 8px;
      cursor: pointer; border-radius: var(--r1);
      padding: 4px 2px; transition: background .15s;
    }
    .sb-obs-row:hover { background: rgba(255,255,255,.04); }
    .sb-obs-label {
      font-size: 9px; font-weight: 700; color: var(--muted);
      text-transform: uppercase; letter-spacing: .8px;
      font-family: var(--mono); flex-shrink: 0;
    }
    .sb-obs-scene {
      font-size: 11px; color: var(--text); font-weight: 600;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1;
      transition: opacity var(--trans);
    }
    .sb-obs-chevron {
      font-size: 8px; color: var(--muted); flex-shrink: 0; transition: opacity var(--trans), transform .15s;
    }
    .sb-obs-chevron.open { transform: rotate(180deg); }
    #nk-sidebar.col .sb-obs-scene,
    #nk-sidebar.col .sb-obs-chevron { opacity: 0; pointer-events: none; }

    /* OBS scene popup */
    .obs-popup {
      display: none; position: absolute;
      bottom: calc(100% + 4px); left: 8px; right: 8px;
      background: var(--card2); border: 1px solid var(--border2);
      border-radius: var(--r2); box-shadow: 0 8px 32px rgba(0,0,0,.7);
      z-index: 9999; overflow: hidden; max-height: 260px; overflow-y: auto;
    }
    .obs-popup.open { display: block; }
    .obs-popup-hd {
      padding: 7px 12px; font-size: 9px; font-weight: 700; color: var(--muted);
      text-transform: uppercase; letter-spacing: .8px;
      border-bottom: 1px solid var(--border); position: sticky; top: 0;
      background: var(--card2);
    }
    .obs-scene-item {
      display: flex; align-items: center; gap: 8px;
      padding: 9px 12px; font-size: 12px; color: var(--muted);
      cursor: pointer; transition: background .12s, color .12s;
    }
    .obs-scene-item:hover { background: rgba(255,255,255,.05); color: var(--text); }
    .obs-scene-item.active { color: var(--cyan); background: rgba(0,200,224,.07); }
    .obs-scene-dot {
      width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
      background: transparent;
    }
    .obs-scene-item.active .obs-scene-dot { background: var(--cyan); }
    .obs-no-scenes {
      padding: 14px 12px; font-size: 11px; color: var(--muted); text-align: center;
    }

    /* Logout button in user area */
    .sb-logout-btn {
      margin-left: auto; flex-shrink: 0; width: 26px; height: 26px;
      background: none; border: 1px solid transparent; border-radius: var(--r1);
      color: var(--muted); cursor: pointer; font-size: 13px;
      display: flex; align-items: center; justify-content: center;
      transition: color .15s, border-color .15s, background .15s;
      opacity: 0.4;
    }
    .sb-user:hover .sb-logout-btn { opacity: 1; }
    .sb-logout-btn:hover { color: var(--red); border-color: rgba(239,68,68,.3); background: rgba(239,68,68,.08); opacity: 1; }
    #nk-sidebar.col .sb-logout-btn { display: none; }

    /* Platform icons in sidebar */
    .sb-plat-ico {
      width: 14px; height: 14px; object-fit: contain; flex-shrink: 0;
      opacity: 0.5; transition: opacity .3s;
    }
    .sb-pdot.live ~ .sb-plat-ico,
    .sb-plat:has(.live) .sb-plat-ico { opacity: 1; }
  `;

  // ─── HTML ─────────────────────────────────────────────────────────────────
  function mkSidebar() {
    const items = NAV.map(n => `
      <a class="sb-item" href="${n.href}" data-page="${n.id}" data-label="${n.label}">
        <span class="sb-icon">${ICONS[n.id] || ""}</span>
        <span class="sb-label">${n.label}</span>
      </a>`).join("");

    return `
    <div id="nk-sidebar">
      <div class="sb-head">
        <div class="sb-logo-mark"><img src="/icones/Logo.png" alt="Nucleus"></div>
        <span class="sb-logo-text">Nucleus</span>
        <button class="sb-col-btn" id="sb-col-btn">◀</button>
      </div>
      <nav class="sb-nav">${items}</nav>
      <div class="sb-plats">
        <div class="sb-plat">
          <div class="sb-pdot" id="sbdot-twitch"></div>
          <img class="sb-plat-ico" src="/icones/twitch.png" alt="">
          <span class="sb-pname">Twitch</span>
        </div>
        <div class="sb-plat">
          <div class="sb-pdot" id="sbdot-youtube"></div>
          <img class="sb-plat-ico" src="/icones/youtube.png" alt="">
          <span class="sb-pname">YouTube</span>
        </div>
        <div class="sb-plat">
          <div class="sb-pdot" id="sbdot-kick"></div>
          <img class="sb-plat-ico" src="/icones/kick.png" alt="">
          <span class="sb-pname">Kick</span>
        </div>
      </div>
      <div class="sb-obs" id="sb-obs">
        <div class="obs-popup" id="obs-popup"></div>
        <div class="sb-obs-row" id="sb-obs-row">
          <span class="sb-obs-label">OBS</span>
          <span class="sb-obs-scene" id="sb-obs-scene">—</span>
          <span class="sb-obs-chevron" id="sb-obs-chevron">▲</span>
        </div>
      </div>
      <div class="sb-update" id="sb-update" onclick="window.open(document.getElementById('sb-update').dataset.url,'_blank')">
        <div class="sb-update-title">⬆ Nova versão disponível</div>
        <div class="sb-update-sub" id="sb-update-sub">Clique para baixar</div>
      </div>
      <div class="sb-user" id="sb-user">
        <div class="sb-avatar" id="sb-avatar">?</div>
        <div class="sb-uinfo" onclick="location.href='/settings'" style="cursor:pointer;flex:1;overflow:hidden">
          <div class="sb-uemail" id="sb-email">—</div>
          <div class="sb-uplan" id="sb-plan">free</div>
        </div>
        <button class="sb-logout-btn" id="sb-logout-btn" title="Sair" onclick="NucleusLogout(event)">⏻</button>
      </div>
    </div>
    <div id="nk-toasts"></div>`;
  }

  const isCol = () => localStorage.getItem(LS_COL) === "1";
  function applyCol(v) {
    const sb = document.getElementById("nk-sidebar");
    if (v) { sb.classList.add("col"); document.body.classList.add("sb-col"); }
    else   { sb.classList.remove("col"); document.body.classList.remove("sb-col"); }
    localStorage.setItem(LS_COL, v ? "1" : "0");
  }

  function markActive() {
    const path = location.pathname;
    for (const n of NAV) {
      const a = document.querySelector(`.sb-item[data-page="${n.id}"]`);
      if (!a) continue;
      a.classList.toggle("active", n.href === "/" ? path === "/" : path.startsWith(n.href));
    }
  }

  async function pollStatus() {
    try {
      const r = await fetch("/stream/status");
      if (!r.ok) return;
      const s = await r.json();
      for (const [p, live] of [["twitch", s.twitch_live], ["youtube", s.youtube_live], ["kick", s.kick_live]]) {
        document.getElementById("sbdot-" + p)?.classList.toggle("live", !!live);
      }
    } catch (_) {}
  }

  function _setUser(email, planType) {
    const eEl = document.getElementById("sb-email");
    const pEl = document.getElementById("sb-plan");
    const av  = document.getElementById("sb-avatar");
    const prem = planType === "premium";
    if (eEl) eEl.textContent = email || "—";
    if (pEl) { pEl.textContent = prem ? "premium ✦" : "free"; pEl.className = "sb-uplan" + (prem ? " premium" : ""); }
    if (av)  av.textContent = (email || "?")[0].toUpperCase();
  }

  function _readSupabaseLocalStorage() {
    // Supabase stores session in localStorage as sb-<ref>-auth-token
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith("sb-") && key.endsWith("-auth-token")) {
          const data = JSON.parse(localStorage.getItem(key) || "{}");
          const user = data?.user || data?.session?.user;
          if (user?.email) return user;
        }
      }
    } catch (_) {}
    return null;
  }

  async function _syncPlanToBackend(isPremium, email, displayName) {
    try {
      await fetch("/auth/plan", { method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({is_premium: isPremium, email: email||"", display_name: displayName||""}) });
    } catch(_) {}
  }

  async function loadUser() {
    try {
      const sb = window._sb;
      if (sb) {
        await new Promise(r => setTimeout(r, 300));
        const { data: { session } } = await sb.auth.getSession();
        if (session?.user) {
          const u = session.user;
          // Busca is_premium direto da tabela profiles
          let isPremium = false;
          try {
            const { data: prof } = await sb.from("profiles").select("is_premium").eq("id", u.id).single();
            isPremium = prof?.is_premium === true;
          } catch(_) {}
          const displayName = u.user_metadata?.display_name || "";
          _setUser(u.email || "", isPremium ? "premium" : "free");
          _syncPlanToBackend(isPremium, u.email, displayName);
          return;
        }
      }

      // Fallback: localStorage
      const lsUser = _readSupabaseLocalStorage();
      if (lsUser) { _setUser(lsUser.email, "free"); return; }

      // Fallback: server endpoint
      const r = await fetch("/auth/me");
      if (r.ok) { const u = await r.json(); if (u.email) _setUser(u.email, u.plan_type); }
    } catch (_) {}
  }

  async function _checkUpdate() {
    try {
      const r = await fetch("/api/version");
      if (!r.ok) return;
      const d = await r.json();
      if (!d.update_available) return;
      const el = document.getElementById("sb-update");
      const sub = document.getElementById("sb-update-sub");
      if (!el) return;
      el.dataset.url = d.download_url || "https://github.com/LuisFP0205/Nucleos/releases/latest";
      if (sub) sub.textContent = `v${d.current} → v${d.latest} · Clique para baixar`;
      el.style.display = "block";
    } catch(_) {}
  }

  window.NucleusLogout = async (e) => {
    if (e) e.stopPropagation();
    try {
      const sb = window._sb;
      if (sb) await sb.auth.signOut();
    } catch (_) {}
    NucleusToast("Saindo...", "info", 1500);
    setTimeout(() => { location.href = "/login"; }, 600);
  };

  // ── Theme toggle ────────────────────────────────────────────────────────────
  const LS_THEME = "nk_theme";
  function _applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem(LS_THEME, t);
  }
  window.NucleusToggleTheme = () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    _applyTheme(cur === "dark" ? "light" : "dark");
  };

  window.NucleusToast = (msg, type = "info", ms = 3000) => {
    const c = document.getElementById("nk-toasts");
    if (!c) return;
    const t = document.createElement("div");
    t.className = `nk-toast ${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .25s"; setTimeout(() => t.remove(), 260); }, ms);
  };

  // ── OBS Scene Switcher ───────────────────────────────────────────────────
  let _obsCurrentScene = "";

  async function loadOBSScene() {
    try {
      const r = await fetch("/obs/status");
      if (!r.ok) return;
      const s = await r.json();
      if (!s.connected) return;
      _obsCurrentScene = s.current_scene || "";
      const el = document.getElementById("sb-obs-scene");
      if (el) el.textContent = _obsCurrentScene || "—";
    } catch (_) {}
  }

  function _closeOBSPopup() {
    document.getElementById("obs-popup")?.classList.remove("open");
    document.getElementById("sb-obs-chevron")?.classList.remove("open");
  }

  async function _openOBSPopup() {
    const popup = document.getElementById("obs-popup");
    if (!popup) return;
    document.getElementById("sb-obs-chevron")?.classList.add("open");
    popup.innerHTML = '<div class="obs-popup-hd">Trocar Cena</div><div class="obs-no-scenes">Carregando...</div>';
    popup.classList.add("open");
    try {
      const r = await fetch("/obs/scenes");
      const scenes = r.ok ? await r.json() : [];
      if (!scenes.length) {
        popup.innerHTML = '<div class="obs-popup-hd">Trocar Cena</div><div class="obs-no-scenes">OBS desconectado</div>';
        return;
      }
      popup.innerHTML = '<div class="obs-popup-hd">Trocar Cena</div>' +
        scenes.map(s => `<div class="obs-scene-item${s === _obsCurrentScene ? " active" : ""}" data-scene="${s.replace(/"/g,"&quot;")}">
          <div class="obs-scene-dot"></div>${s}</div>`).join("");
      popup.querySelectorAll(".obs-scene-item").forEach(el => {
        el.addEventListener("click", e => {
          e.stopPropagation();
          _switchOBSScene(el.dataset.scene);
        });
      });
    } catch (_) {
      popup.innerHTML = '<div class="obs-popup-hd">Trocar Cena</div><div class="obs-no-scenes">Erro ao carregar</div>';
    }
  }

  async function _switchOBSScene(name) {
    _closeOBSPopup();
    try {
      const r = await fetch("/obs/scene", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scene: name })
      });
      if (r.ok) {
        _obsCurrentScene = name;
        const el = document.getElementById("sb-obs-scene");
        if (el) el.textContent = name;
        NucleusToast("Cena: " + name, "ok", 2000);
      } else {
        NucleusToast("Erro ao trocar cena", "error");
      }
    } catch (_) { NucleusToast("OBS desconectado", "error"); }
  }

  // Sincroniza canais do Supabase → backend (roda a cada abertura do app)
  async function _syncChannelsFromSupabase() {
    try {
      const sb = window._sb;
      if (!sb) return;
      const { data: { session } } = await sb.auth.getSession();
      if (!session) return;

      const { data } = await sb.from('profiles').select(
        'twitch_channel, youtube_channel_id, kick_channel, chat_twitch, chat_youtube, chat_kick'
      ).single();
      if (!data) return;

      // Só sincroniza se tiver pelo menos um canal configurado no Supabase
      if (!data.twitch_channel && !data.youtube_channel_id && !data.kick_channel) return;

      await fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          twitch_channel:     data.twitch_channel      || '',
          youtube_channel_id: data.youtube_channel_id  || '',
          kick_channel:       data.kick_channel         || '',
          chat_twitch:        data.chat_twitch  ?? true,
          chat_youtube:       data.chat_youtube ?? true,
          chat_kick:          data.chat_kick    ?? true,
        }),
      });
    } catch (_) {}
  }

  function init() {
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.insertBefore(style, document.head.firstChild);

    const tmp = document.createElement("div");
    tmp.innerHTML = mkSidebar();
    while (tmp.firstChild) document.body.insertBefore(tmp.firstChild, document.body.firstChild);

    // Apply saved theme before render
    _applyTheme(localStorage.getItem(LS_THEME) || "dark");

    applyCol(isCol());
    document.getElementById("sb-col-btn").addEventListener("click", () => applyCol(!isCol()));
    markActive();
    pollStatus();
    setInterval(pollStatus, 30000);
    loadUser();
    loadOBSScene();
    _syncChannelsFromSupabase();
    _checkUpdate();

    // OBS popup toggle
    document.getElementById("sb-obs-row").addEventListener("click", () => {
      const popup = document.getElementById("obs-popup");
      if (popup?.classList.contains("open")) _closeOBSPopup();
      else _openOBSPopup();
    });

    // Close OBS popup on outside click
    document.addEventListener("click", e => {
      const obs = document.getElementById("sb-obs");
      if (obs && !obs.contains(e.target)) _closeOBSPopup();
    });
  }

  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
