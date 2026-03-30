<<<<<<< HEAD
# Nucleus

Servidor local para streamers que conecta **Twitch**, **YouTube** e **Kick** ao OBS Studio via overlays HTML em tempo real.

Detecta automaticamente quando você está ao vivo em qualquer plataforma, lê o chat de todas simultaneamente, mostra a música tocando no seu PC e exibe tudo em overlays transparentes no OBS — sem configuração manual durante a live.

---

## Sumário

- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Como iniciar](#como-iniciar)
- [Funcionalidades](#funcionalidades)
  - [Auto-detecção de Live](#auto-detecção-de-live)
  - [Contador de Espectadores e Uptime](#contador-de-espectadores-e-uptime)
  - [Detector de Música](#detector-de-música)
  - [Chat em Tempo Real (WebSocket)](#chat-em-tempo-real-websocket)
- [Overlays para OBS](#overlays-para-obs)
  - [Chat](#overlay-de-chat)
  - [Música](#overlay-de-música)
  - [Espectadores (Drag & Drop)](#overlay-de-espectadores)
- [Dashboard](#dashboard)
- [Pré-visualização dos Overlays](#pré-visualização-dos-overlays)
- [Gerenciamento de API Keys](#gerenciamento-de-api-keys)
- [Terminal de Logs](#terminal-de-logs)
- [Autenticação Twitch (OAuth)](#autenticação-twitch-oauth)
- [Endpoints da API](#endpoints-da-api)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Arquitetura interna](#arquitetura-interna)
- [Distribuição (PyInstaller)](#distribuição-pyinstaller)
- [Perguntas frequentes](#perguntas-frequentes)

---

## Requisitos

| Requisito | Versão mínima |
|---|---|
| Python | 3.11+ |
| Sistema operacional | Windows 10 / 11 |
| OBS Studio | Qualquer versão com Browser Source |

> O detector de música usa a API nativa do Windows (GSMTC), por isso o sistema **só funciona no Windows**.

---

## Instalação

### 1. Clone ou baixe o projeto

```bash
git clone https://github.com/seu-usuario/nucleus.git
cd nucleus
```

### 2. Crie um ambiente virtual (recomendado)

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

Pacotes instalados:

| Pacote | Para que serve |
|---|---|
| `fastapi` | Framework web assíncrono |
| `uvicorn[standard]` | Servidor ASGI com suporte a WebSocket e hot-reload |
| `httpx` | Requisições HTTP assíncronas para as APIs |
| `curl-cffi` | Requisições HTTP imitando fingerprint TLS do Chrome (contorna Cloudflare do Kick) |
| `pydantic-settings` | Leitura e validação do arquivo `.env` |
| `websockets` | Chat IRC da Twitch e chat Pusher do Kick |
| `winsdk` | Acesso à API de mídia do Windows (GSMTC) |
| `google-api-python-client` | YouTube Data API v3 |
| `google-auth` | Autenticação Google |
| `pywebview` | Janela nativa para o executável PyInstaller |

---

## Configuração

### 1. Crie o arquivo `.env`

Copie o arquivo de exemplo e preencha suas credenciais:

```bash
copy .env.example .env
```

Conteúdo do `.env`:

```env
# ── Twitch ─────────────────────────────────────────────────────────────
TWITCH_CLIENT_ID=seu_client_id_aqui
TWITCH_CLIENT_SECRET=seu_client_secret_aqui
TWITCH_CHANNEL=nome_do_seu_canal

# ── YouTube ────────────────────────────────────────────────────────────
YOUTUBE_API_KEY=sua_api_key_aqui
YOUTUBE_CHANNEL_ID=UCxxxxxxxxxxxxxxxxxxxxxxxx

# ── Kick ───────────────────────────────────────────────────────────────
# Basta o slug do canal — não requer API key
KICK_CHANNEL=nome_do_seu_canal_kick

# ── Servidor ───────────────────────────────────────────────────────────
PORT=3000
HOST=0.0.0.0
```

> **Kick não requer credenciais.** A API pública do Kick é acessada sem autenticação. Basta definir o nome do canal.

> **Alternativa ao `.env`:** as credenciais de Twitch e YouTube também podem ser configuradas pela interface em `http://localhost:3000/keys-config` sem editar arquivos manualmente. Veja a seção [Gerenciamento de API Keys](#gerenciamento-de-api-keys).

### 2. Como obter as credenciais

#### Twitch — Client ID e Client Secret

1. Acesse [dev.twitch.tv/console](https://dev.twitch.tv/console)
2. Clique em **Register Your Application**
3. Preencha:
   - **Name:** `nucleus` (qualquer nome)
   - **OAuth Redirect URLs:** `http://localhost`
   - **Category:** `Chat Bot` ou `Other`
4. Clique em **Create** e depois em **Manage**
5. Copie o **Client ID** e clique em **New Secret** para gerar o Client Secret

> A Redirect URL `http://localhost:3000/auth/twitch/callback` deve ser cadastrada **exatamente** assim.

#### YouTube — API Key

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto (ou use um existente)
3. Vá em **APIs e Serviços → Biblioteca**
4. Ative a **YouTube Data API v3**
5. Vá em **APIs e Serviços → Credenciais**
6. Clique em **Criar Credenciais → Chave de API**
7. Copie a chave gerada

#### YouTube — Channel ID

1. Acesse seu canal no YouTube
2. Clique em **Personalizar canal → Informações básicas**
3. O Channel ID está na URL: `youtube.com/channel/UCxxxxxxx`

#### Kick — Canal

Basta o **slug** (nome de usuário) do canal. Exemplo: se a URL do seu canal é `kick.com/seucanalaqui`, use `KICK_CHANNEL=seucanalaqui`.

---

## Como iniciar

### Opção 1 — Direto com Python

```bash
python main.py
```

Abre o dashboard automaticamente no navegador padrão.

### Opção 2 — Com uvicorn (recomendado para produção)

```bash
uvicorn main:app --host 0.0.0.0 --port 3000
```

### Opção 3 — Com hot-reload (desenvolvimento)

```bash
uvicorn main:app --host 0.0.0.0 --port 3000 --reload
```

Após iniciar, acesse o dashboard em:

```
http://localhost:3000
```

Você verá no terminal mensagens como:

```
[INFO] [Startup] Twitch channel: 'seucanalaqui'
[INFO] [Startup] YouTube channel: 'UCxxxxxxxxxxxxxxxxxxxxxxxx'
[INFO] [Startup] Kick channel: 'seucanalakick'
[INFO] [Startup] Stream detection loop started (interval=30s)
[INFO] [AutoDetect] Twitch live detectada: Título da live
[INFO] [AutoDetect] Iniciando chat Kick (chatroom_id=123456)
```

---

## Funcionalidades

---

### Auto-detecção de Live

> Arquivos: [routers/stream.py](routers/stream.py) · [services/twitch_service.py](services/twitch_service.py) · [services/youtube_service.py](services/youtube_service.py) · [services/kick_service.py](services/kick_service.py)

O servidor verifica automaticamente a cada **30 segundos** se você está ao vivo em qualquer plataforma configurada.

#### O que acontece quando detecta uma live

```
Servidor inicia
    │
    └─► Loop de detecção (a cada 30s)
            ├─► Twitch: GET /helix/streams?user_login=seu_canal
            │       ├─ Ao vivo? → inicia listener IRC do chat
            │       └─ Offline? → para o listener
            │
            ├─► YouTube: RSS feed + GET /videos?part=liveStreamingDetails
            │       ├─ Ao vivo? → obtém liveChatId → inicia polling do chat
            │       └─ Offline? → para o polling
            │
            └─► Kick: GET kick.com/api/v2/channels/{slug}
                    ├─ Ao vivo? → obtém chatroom_id → conecta ao Pusher WebSocket
                    └─ Offline? → desconecta do Pusher
```

#### Como funciona a detecção da Twitch

1. Obtém um **App Access Token** via `client_credentials` (OAuth machine-to-machine)
2. Faz `GET /helix/streams?user_login=seu_canal`
3. Se retornar dados, o canal está ao vivo. Retorna `viewer_count` e `started_at`

#### Como funciona a detecção do YouTube

Usa **RSS + videos.list** (custo: 1 unidade de API por checagem, vs 100 do endpoint search):

1. Busca os últimos 5 vídeos do canal via RSS (gratuito, sem cota)
2. Checa `GET /videos?part=liveStreamingDetails` para esses IDs
3. Se algum tiver `activeLiveChatId`, está ao vivo. Retorna `concurrentViewers` e `actualStartTime`

#### Como funciona a detecção do Kick

A API pública do Kick não requer autenticação, mas usa Cloudflare. O `curl-cffi` imita a fingerprint TLS do Chrome para contornar a proteção:

1. `GET https://kick.com/api/v2/channels/{slug}` com headers de browser via `curl-cffi`
2. Se `livestream` não for null, o canal está ao vivo
3. `chatroom.id` é usado para conectar ao chat via Pusher

#### Forçar checagem imediata

```http
POST http://localhost:3000/stream/detect-now
```

O botão **↺** no dashboard chama este endpoint.

#### Endpoint de status

```http
GET http://localhost:3000/stream/status
```

Resposta:

```json
{
  "youtube_live": true,
  "twitch_live": false,
  "kick_live": true,
  "youtube_video_id": "dQw4w9WgXcQ",
  "youtube_live_chat_id": "Cg0KC...",
  "twitch_stream_id": null,
  "kick_stream_id": "12345",
  "twitch_viewers": 0,
  "youtube_viewers": 842,
  "kick_viewers": 213,
  "twitch_live_since": null,
  "youtube_live_since": "2025-03-11T18:00:00Z",
  "kick_live_since": "2025-03-11T17:45:00Z",
  "twitch_title": null,
  "twitch_game": null,
  "youtube_title": "Live de hoje",
  "kick_title": "Jogando com os inscritos"
}
```

---

### Contador de Espectadores e Uptime

O campo `*_viewers` em `/stream/status` traz o número de espectadores de cada plataforma:

| Plataforma | Fonte dos viewers | Fonte do uptime |
|---|---|---|
| Twitch | `viewer_count` da Helix API | `started_at` da Helix API |
| YouTube | `concurrentViewers` de `liveStreamingDetails` | `actualStartTime` de `liveStreamingDetails` |
| Kick | `viewer_count` de `livestream` na API pública | `created_at` de `livestream` |

O dashboard exibe os contadores **e um timer de uptime real** (calculado a partir do horário de início real da live retornado pela API) nos cards de cada plataforma.

O Overlay de Espectadores exibe os números diretamente no OBS e se oculta automaticamente quando a plataforma está offline.

---

### Detector de Música

> Arquivo: [services/music_service.py](services/music_service.py) · [routers/music.py](routers/music.py)

Captura em tempo real as informações da mídia tocando no Windows via **Global System Media Transport Controls (GSMTC)**.

#### Modos de detecção

| Modo | Comportamento |
|---|---|
| **Auto-detect** (padrão) | Detecta automaticamente o player ativo com mais prioridade |
| **Player fixo** | Exibe sempre as informações de um player específico, ignorando os demais |

O modo é configurável no dashboard (seção **Música Tocando**) sem reiniciar o servidor.

#### Players suportados

Qualquer player que registre sessão no Windows GSMTC é detectado automaticamente:

| Player | Detectado como |
|---|---|
| Spotify | `Spotify` |
| VLC Media Player | `VLC` |
| Google Chrome | `Chrome` |
| Microsoft Edge | `Edge` |
| Mozilla Firefox | `Firefox` |
| foobar2000 | `foobar2000` |
| MusicBee | `MusicBee` |
| Outros | Nome derivado do executável |

#### Dados capturados

| Campo | Tipo | Descrição |
|---|---|---|
| `title` | string | Título da música |
| `artist` | string | Nome do artista |
| `album` | string | Nome do álbum |
| `player` | string | Nome do player |
| `thumbnail` | string | Capa do álbum em base64 |
| `duration` | int | Duração total em segundos |
| `position` | int | Posição atual em segundos |
| `is_playing` | bool | `true` se tocando, `false` se pausado |

#### Endpoints

```http
GET  /music/current          → Música tocando no momento
GET  /music/players          → Lista todos os players com sessão GSMTC ativa
GET  /music/settings         → Configuração atual (auto-detect e player fixo)
POST /music/select           → Define player fixo ou ativa auto-detect
```

Exemplo de resposta de `/music/current`:

```json
{
  "title": "Believer",
  "artist": "Imagine Dragons",
  "album": "Evolve",
  "player": "Spotify",
  "thumbnail": "data:image/jpeg;base64,/9j/...",
  "duration": 204,
  "position": 87,
  "is_playing": true
}
```

---

### Chat em Tempo Real (WebSocket)

> Arquivo: [routers/chat.py](routers/chat.py)

O chat usa **WebSocket** para entregar mensagens instantaneamente a todos os overlays e ao dashboard.

#### Fluxo completo

```
Twitch IRC ──────────────┐
YouTube API polling ─────┤──► broadcast() ──► ChatManager ──► WebSocket ──► Overlay/Dashboard
Kick Pusher WebSocket ───┘         │
                                    └──► Histórico (últimas 100 msgs)
```

#### Emotes customizados

Cada plataforma processa os emotes antes de enviar a mensagem:

| Plataforma | Formato no chat | Processamento |
|---|---|---|
| Twitch | Tag IRC `@emotes=id:start-end` | Substituição por posição de caractere |
| Kick | `[emote:id:nome]` no conteúdo | Regex + substituição |
| YouTube | Sem emotes customizados | Texto escapado normalmente |

O campo `message_html` contém HTML seguro com as tags `<img>` dos emotes já inseridas.

#### Filtro por plataforma

Cada plataforma tem um toggle independente. O `broadcast()` verifica `_platform_enabled` antes de entregar a mensagem — se uma plataforma estiver desativada, suas mensagens são descartadas antes de chegar ao WebSocket.

Os toggles são persistidos em `runtime_settings.json` e sobrevivem a reinicializações do servidor.

#### Chat da Twitch — IRC sobre WebSocket

Protocolo IRC sobre `wss://irc-ws.chat.twitch.tv:443` com capabilities `twitch.tv/tags` e `twitch.tv/commands`. Sem token configurado, conecta anonimamente (`justinfan12345`) para leitura.

#### Chat do YouTube — Polling da API

Endpoint `liveChat/messages`. Intervalo dinâmico via `pollingIntervalMillis` (mínimo 3s). Se a API retornar 403 (cota excedida), aguarda 60 segundos automaticamente.

#### Chat do Kick — Pusher WebSocket

O Kick usa **Pusher** para entregar mensagens do chat:

- **URL:** `wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679`
- **Canal Pusher:** `chatrooms.{chatroom_id}.v2`
- **Evento:** `App\Events\ChatMessageEvent`
- Não requer autenticação — apenas o `chatroom_id` obtido na detecção da live

#### Formato das mensagens WebSocket

```json
{
  "platform": "twitch",
  "user": "usuario123",
  "message": "Boa live! nukadaveLove",
  "message_html": "Boa live! <img class=\"chat-emote\" src=\"https://static-cdn.jtvnw.net/...\" alt=\"nukadaveLove\">",
  "color": "#9147FF",
  "badges": ["subscriber"]
}
```

| Campo | Descrição |
|---|---|
| `platform` | `"twitch"`, `"youtube"` ou `"kick"` |
| `message` | Texto puro original |
| `message_html` | HTML com emotes substituídos por `<img>` (use `innerHTML` no frontend) |
| `color` | Cor hex do nome do usuário |
| `badges` | Lista de badges do usuário (ex: `"moderator"`, `"subscriber"`) |

#### Endpoints de chat

| Método | URL | Descrição |
|---|---|---|
| `WS` | `/ws/chat` | WebSocket em tempo real |
| `GET` | `/chat/history` | Últimas 100 mensagens (REST) |

#### Exemplo de conexão em JavaScript

```javascript
const ws = new WebSocket('ws://localhost:3000/ws/chat');

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    // Usa message_html para renderizar emotes; fallback para texto escapado
    element.innerHTML = msg.message_html ?? escapeHtml(msg.message);
};

ws.onclose = () => setTimeout(() => connect(), 3000);
```

---

## Overlays para OBS

### Como adicionar um overlay no OBS

1. No OBS, clique em **+** na lista de **Fontes**
2. Selecione **Navegador** (Browser Source)
3. Cole a URL do overlay
4. Ajuste largura e altura conforme indicado abaixo

> Para visualizar todos os overlays com as URLs prontas para copiar, acesse `http://localhost:3000/previews`.

---

### Overlay de Chat

```
URL:     http://localhost:3000/overlay/chat
Largura: 420px
Altura:  600px (ou mais, conforme o espaço disponível na cena)
```

- Fundo transparente
- Mensagens entram pelo topo com animação slide-in
- Cada mensagem some automaticamente após o timeout configurado
- Limite máximo de mensagens visíveis (configurável no dashboard)
- Suporta emotes customizados da Twitch e Kick como imagens
- Ícone de plataforma ao lado do nome de cada usuário
- Barra colorida lateral por plataforma:
  - Twitch: roxo `#9147ff`
  - YouTube: vermelho `#ff0000`
  - Kick: verde `#00e701`
- Reconecta ao WebSocket automaticamente

---

### Overlay de Música

```
URL:     http://localhost:3000/overlay/music
Largura: 340px
Altura:  80px
```

- Fundo semi-transparente com capa do álbum, título, artista e nome do player
- Aparece automaticamente quando uma música começa
- Some automaticamente quando nada está tocando
- Atualiza a cada 3 segundos

---

### Overlay de Espectadores

```
URL:     http://localhost:3000/overlay/viewers
Largura: livre (recomendado 200 × 130 px como ponto de partida)
```

- Fundo transparente
- Exibe uma linha por plataforma **somente quando essa plataforma está ao vivo**
- Cada linha tem ícone da plataforma, ponto pulsante colorido e contagem de espectadores
- Se nenhuma plataforma estiver ao vivo, o overlay fica completamente invisível
- Atualiza a cada 15 segundos

#### Posicionamento livre (Drag & Drop)

As posições de cada componente (Twitch, YouTube, Kick) são **completamente livres** e independentes. Para reposicionar:

1. Acesse `http://localhost:3000/previews` e clique em **✏ Editar posições**
2. Arraste os componentes para a posição desejada
3. Clique em **💾 Salvar**

As posições são salvas no servidor (`overlay_viewers_positions.json`) e sincronizadas automaticamente com o OBS Browser Source — o OBS sempre lê as mesmas posições do servidor, sem conflito de `localStorage`.

#### Layouts predefinidos

Na toolbar de edição há atalhos para aplicar layouts instantaneamente:

| Layout | Descrição |
|---|---|
| ⬇ Vertical | Componentes empilhados verticalmente à esquerda |
| ➡ Horizontal | Componentes lado a lado na horizontal |
| ↗ Escada | Componentes em diagonal crescente |
| ↺ Reset | Restaura as posições padrão |

#### Controle pelo dashboard

O dashboard também tem uma modal de pré-visualização com toolbar de edição integrada — é possível ajustar as posições sem sair do dashboard.

---

## Dashboard

Acesse em `http://localhost:3000`

O dashboard ocupa a **tela inteira** (altura da viewport) com layout em duas colunas e o chat rolável internamente.

### Coluna esquerda

#### Status das Lives
Três cards independentes — Twitch, YouTube e Kick — cada um com:
- Indicador luminoso pulsante (acende quando ao vivo)
- Label "Ao vivo" / "Offline"
- Contador de espectadores em tempo real
- Timer de uptime da live (tempo real desde o início da transmissão, atualizado a cada segundo)
- Tag "LIVE" / "OFF"

Atualiza a cada 30 segundos. Botão **↺** força checagem imediata.

#### Overlays
Links rápidos para abrir a pré-visualização dos três overlays e copiar as URLs para o OBS.

#### Música Tocando
Exibe capa, título e artista da mídia atual. Atualiza a cada 3 segundos.

Inclui controles de player:
- **Checkbox de auto-detect** — quando ativo, detecta automaticamente o player com mídia em andamento
- **Botão de seleção manual** — abre lista de players ativos para fixar um específico

### Coluna direita

#### Configuração de Canais
Campos para definir o canal da Twitch, Channel ID do YouTube e slug do Kick em runtime, sem reiniciar o servidor.

#### Toggles de Chat
Chips clicáveis para ativar/desativar cada plataforma no feed de chat:
- **Twitch** (roxo)
- **YouTube** (vermelho)
- **Kick** (verde)

A desativação é imediata — o backend para de entregar mensagens daquela plataforma. A configuração é persistida em `runtime_settings.json`.

#### Configurações do Overlay de Chat
Sliders inline para ajustar **timeout** (5–120s) e **máximo de mensagens** (5–50) do overlay de chat.

#### Feed de Chat
Feed unificado com mensagens de todas as plataformas em tempo real via WebSocket:
- Ícones de plataforma (`twitch.png`, `youtube.png`, `kick.png`)
- Nome do usuário colorido
- Emotes customizados exibidos como imagens
- Histórico das últimas 100 mensagens ao conectar
- **Scroll automático** para o final a cada nova mensagem
- **Scroll manual** pausa o auto-scroll; voltar ao final o retoma
- Status da conexão WebSocket no cabeçalho

---

## Pré-visualização dos Overlays

Acesse em `http://localhost:3000/previews`

Página com os três overlays renderizados em iframes para conferência antes de adicionar no OBS:

- **Chat** — preview em 420×420 px com fundo xadrez (representa transparência)
- **Música** — preview em 340×80 px
- **Espectadores** — preview em largura total com toolbar de edição integrada

Cada card inclui:
- Dimensões recomendadas para o OBS
- URL pronta com botão **Copiar**
- Para o Viewers: toolbar completa com botões de edição, layouts e salvar

---

## Gerenciamento de API Keys

Acesse em `http://localhost:3000/keys-config`

Interface web para configurar as credenciais de Twitch e YouTube **sem editar o arquivo `.env` manualmente**:

- **Twitch Client ID** — exibido em texto limpo
- **Twitch Client Secret** — mascarado (ex: `abc****xyz`)
- **YouTube API Key** — mascarado

Campos em branco ao salvar **preservam o valor atual** — não é necessário redigitar uma chave para alterar outra.

Após salvar, clique em **Reiniciar servidor** para aplicar as novas credenciais. O servidor reinicia automaticamente e reabre o dashboard na mesma página.

> As chaves ficam salvas no arquivo `.env`. O Kick não usa credenciais e não aparece nesta tela.

---

## Terminal de Logs

Acesse em `http://localhost:3000/logs`

Terminal em tempo real que exibe todos os logs do servidor via WebSocket (`/ws/logs`):

- Mantém histórico dos últimos **500 registros**
- Exibe o histórico completo ao conectar
- Streaming contínuo de novos logs enquanto o servidor roda
- Útil para acompanhar a detecção de lives, conexões de chat e erros sem abrir o terminal

---

## Autenticação Twitch (OAuth)

> O token é obtido via OAuth 2.0 Authorization Code Flow diretamente no dashboard.

### Por que precisa de um token?

Sem token, o servidor conecta ao chat da Twitch anonimamente (`justinfan12345`), suficiente para **leitura**. Com token de usuário, você aparece com seu próprio nome no chat e pode enviar mensagens.

### Como autenticar

1. Inicie o servidor
2. Acesse `http://localhost:3000`
3. Clique em **Conectar com Twitch**
4. Autorize na página oficial da Twitch
5. O servidor troca o código pelo token e o chat IRC reconecta automaticamente

### Scopes solicitados

| Scope | Para que serve |
|---|---|
| `chat:read` | Ler mensagens do chat como usuário identificado |

### Redirect URI obrigatória

Cadastre no [Twitch Developer Console](https://dev.twitch.tv/console):

```
http://localhost
```

> A Twitch trata `localhost` como caso especial de desenvolvimento — aceita qualquer porta e caminho automaticamente.

### Duração do token

O token fica em memória enquanto o servidor roda. Ao reiniciar, é necessário autenticar novamente (não é salvo em disco por segurança).

---

## Endpoints da API

| Método | URL | Descrição |
|---|---|---|
| `GET` | `/` | Dashboard principal |
| `GET` | `/previews` | Pré-visualização de todos os overlays |
| `GET` | `/keys-config` | Página de gerenciamento de API Keys |
| `GET` | `/logs` | Terminal de logs em tempo real |
| `GET` | `/stream/status` | Status das lives (Twitch + YouTube + Kick) |
| `POST` | `/stream/detect-now` | Força checagem imediata |
| `GET` | `/music/current` | Música tocando no momento |
| `GET` | `/music/players` | Lista players GSMTC ativos |
| `GET` | `/music/settings` | Configuração atual do detector de música |
| `POST` | `/music/select` | Define player fixo ou ativa auto-detect |
| `GET` | `/chat/history` | Últimas 100 mensagens |
| `WS` | `/ws/chat` | WebSocket de chat em tempo real |
| `WS` | `/ws/logs` | WebSocket de logs em tempo real |
| `GET` | `/settings` | Configurações atuais (canais + toggles) |
| `POST` | `/settings` | Atualiza configurações em runtime |
| `GET` | `/keys` | Retorna API Keys atuais (secrets mascarados) |
| `POST` | `/keys` | Salva API Keys no `.env` |
| `POST` | `/keys/restart` | Reinicia o processo do servidor |
| `GET` | `/overlay/chat` | Overlay HTML do chat |
| `GET` | `/overlay/music` | Overlay HTML da música |
| `GET` | `/overlay/viewers` | Overlay HTML de espectadores |
| `GET` | `/overlay/viewers/positions` | Retorna posições salvas dos componentes |
| `POST` | `/overlay/viewers/positions` | Salva posições dos componentes |
| `GET` | `/auth/twitch` | Inicia OAuth da Twitch |
| `GET` | `/auth/twitch/callback` | Callback OAuth da Twitch |
| `GET` | `/auth/twitch/status` | Status de autenticação |
| `DELETE` | `/auth/twitch` | Remove token (logout) |
| `GET` | `/docs` | Swagger UI |

> Os endpoints de overlay servem os arquivos HTML com `Cache-Control: no-cache` para garantir que o OBS sempre carregue a versão mais recente.

---

## Estrutura do projeto

```
Nucleus/
│
├── main.py                        # Ponto de entrada — FastAPI, routers, lifespan
├── config.py                      # Lê .env via pydantic-settings
├── requirements.txt
├── .env.example
├── runtime_settings.json          # Canais e toggles salvos em runtime (gerado automaticamente)
├── overlay_viewers_positions.json # Posições dos componentes do overlay Viewers (gerado automaticamente)
│
├── models/
│   └── schemas.py                 # StreamStatus, MusicInfo, ChatMessage
│
├── services/
│   ├── twitch_service.py          # OAuth, detecção de live, IRC chat, parsing de emotes
│   ├── youtube_service.py         # RSS + videos.list, polling liveChat/messages
│   ├── kick_service.py            # API pública (curl-cffi), Pusher WebSocket, parsing de emotes
│   └── music_service.py           # GSMTC Windows, multi-sessão, thumbnail base64
│
├── routers/
│   ├── stream.py                  # GET /stream/status, POST /stream/detect-now
│   │                              # detection_loop(): Twitch + YouTube + Kick
│   ├── music.py                   # GET /music/current, /players, /settings — POST /music/select
│   ├── chat.py                    # WS /ws/chat, GET /chat/history
│   │                              # ChatManager, _platform_enabled filter
│   ├── settings.py                # GET/POST /settings — canais + toggles em runtime
│   ├── auth.py                    # GET /auth/twitch — OAuth Authorization Code Flow
│   ├── keys.py                    # GET/POST /keys — gerenciamento de API Keys no .env
│   └── logs.py                    # WS /ws/logs — streaming de logs em tempo real
│
├── overlays/
│   ├── chat.html                  # Overlay de chat (WebSocket, fundo transparente, emotes)
│   ├── music.html                 # Overlay de música (polling REST)
│   └── viewers.html               # Overlay de espectadores (drag & drop, posições via servidor)
│
├── static/
│   ├── dashboard.html             # Dashboard completo (status, uptime, chat, música)
│   ├── previews.html              # Pré-visualização de overlays com URLs para OBS
│   ├── keys.html                  # Interface de gerenciamento de API Keys
│   └── logs.html                  # Terminal de logs em tempo real
│
└── Icones/
    ├── twitch.png
    ├── youtube.png
    └── kick.png
```

---

## Arquitetura interna

### Ciclo de vida da aplicação

```
uvicorn inicia
    │
    └─► lifespan() startup
            ├─ Lê runtime_settings.json (fallback: .env)
            ├─ Cria TwitchService, YouTubeService, KickService
            ├─ Aplica toggles de chat salvos
            ├─ Salva instâncias em app.state
            └─ Inicia detection_loop() como asyncio.Task

uvicorn recebe CTRL+C
    └─► lifespan() shutdown
            ├─ Cancela detection_loop()
            ├─ Para chat Twitch (IRC)
            ├─ Para chat YouTube (polling)
            └─ Para chat Kick (Pusher)
```

### Fluxo de uma mensagem de chat

```
[Kick Pusher WebSocket]
        │
        ▼
_pusher_loop() recebe App\Events\ChatMessageEvent
        │
        ▼
Extrai user, content, color, badges
_build_kick_html() → substitui [emote:id:nome] por <img>
        │
        ▼
broadcast(dict)  ← verifica _platform_enabled
        │
        ▼
ChatManager.broadcast()
        │
        ├─► ws.send_json() → overlay chat.html no OBS
        ├─► ws.send_json() → dashboard no browser
        └─► _history.append() (deque maxlen=100)
```

### Posições do overlay Viewers

```
Editor (previews.html ou dashboard modal)
        │
        ▼
Drag & Drop → mouseup → savePositions()
        │
        ▼
POST /overlay/viewers/positions → overlay_viewers_positions.json
        │
        ▼
OBS Browser Source → GET /overlay/viewers/positions → aplica posições
```

Ao contrário do `localStorage` (isolado por contexto de browser), as posições ficam no servidor — qualquer contexto (OBS, preview, dashboard) lê e escreve no mesmo arquivo.

### Threading e assincronismo

Toda a aplicação é **100% assíncrona** (asyncio). Não há threads bloqueantes:

- `detection_loop` roda em paralelo com requisições HTTP
- IRC da Twitch, polling do YouTube e Pusher do Kick rodam como `asyncio.Task` independentes
- `await asyncio.sleep()` libera o event loop entre intervalos

---

## Distribuição (PyInstaller)

O projeto pode ser empacotado como um executável Windows com **PyInstaller + pywebview**, abrindo uma janela nativa sem depender de um browser externo.

### Gerar o executável

```bash
pip install pyinstaller pywebview
pyinstaller nucleus.spec
```

O executável ficará em `dist/Nucleus/Nucleus.exe`.

### Importante: copiar a pasta inteira

O PyInstaller no modo `--onedir` (padrão) gera uma pasta `dist/Nucleus/` com o executável e uma pasta `_internal/` com todas as dependências. **Você deve copiar a pasta `dist/Nucleus/` completa** — copiar apenas o `.exe` causará o erro `Failed to load Python DLL`.

### Comportamento no modo executável

- O servidor uvicorn sobe em uma thread daemon
- A janela pywebview abre o dashboard automaticamente
- Fechar a janela encerra o servidor
- O botão **Reiniciar** (em `/keys-config`) relança o processo preservando a URL atual

---

## Perguntas frequentes

**O sistema funciona se eu só tiver uma plataforma configurada?**
Sim. Se uma variável de ambiente estiver vazia (ex: `KICK_CHANNEL=`), aquela plataforma é silenciosamente ignorada no loop de detecção.

**O Kick requer alguma conta ou API key?**
Não. A API pública do Kick funciona sem autenticação. Basta o slug do canal.

**O detector de música funciona com YouTube no navegador?**
Sim, desde que o Chrome ou Edge estejam reportando a sessão de mídia ao Windows. Na maioria dos casos funciona automaticamente.

**O chat do YouTube tem delay?**
O polling respeita o `pollingIntervalMillis` da API (geralmente 3–5 segundos). Não é instantâneo como IRC/Pusher, mas é o limite da API.

**Posso rodar em outra porta?**
Sim. Defina `PORT=8080` no `.env`. Lembre de atualizar as URLs no OBS.

**Como configurar os canais sem reiniciar o servidor?**
Use os campos de configuração no dashboard e clique em **Save & Apply**. As mudanças são aplicadas imediatamente e salvas em `runtime_settings.json`.

**Como atualizar as API Keys sem editar o `.env`?**
Acesse `http://localhost:3000/keys-config`, preencha os campos e clique em **Salvar**. Depois clique em **Reiniciar servidor** para aplicar.

**Por que as posições do overlay Viewers não aparecem no OBS?**
O OBS Browser Source tem `localStorage` isolado. Por isso as posições são salvas no servidor (arquivo `overlay_viewers_positions.json`) e carregadas via fetch — funcionam em qualquer contexto.

**Como ver os logs em tempo real?**
Acesse `http://localhost:3000/logs` pelo browser. Ou acompanhe o terminal onde o servidor foi iniciado. Prefixos como `[AutoDetect]`, `[Twitch IRC]`, `[YouTube Chat]`, `[Kick Chat]` e `[WS]` identificam a origem.

**O servidor consome muita CPU/memória?**
Não. Por ser totalmente assíncrono, fica ocioso entre intervalos. Consumo típico abaixo de 50 MB de RAM e menos de 1% de CPU.

**Os overlays são atualizados automaticamente no OBS ao mudar os arquivos?**
Sim. Os endpoints de overlay servem os arquivos com `Cache-Control: no-cache`, garantindo que o OBS sempre busque a versão mais recente ao recarregar.
=======
# Nucleos
>>>>>>> f8ea7cd2293f80d65e585e351b577043f9b1b948
