-- ============================================================
-- Nucleus · Setup do Supabase
-- Execute este arquivo no SQL Editor do seu projeto Supabase:
--   supabase.com → seu projeto → SQL Editor → New query
-- ============================================================


-- ── 1. Tabela de perfis ──────────────────────────────────────
-- Armazena dados extras dos usuários (ex: is_premium).
-- Criada automaticamente para cada novo usuário via trigger.

create table if not exists public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  is_premium boolean not null default false,
  created_at timestamptz not null default now()
);

-- Colunas extras
alter table public.profiles add column if not exists username           text;
alter table public.profiles add column if not exists twitch_channel     text;
alter table public.profiles add column if not exists youtube_channel_id text;
alter table public.profiles add column if not exists kick_channel       text;
alter table public.profiles add column if not exists chat_twitch        boolean;
alter table public.profiles add column if not exists chat_youtube       boolean;
alter table public.profiles add column if not exists chat_kick          boolean;
alter table public.profiles add column if not exists chat_timeout       integer;
alter table public.profiles add column if not exists chat_max_messages  integer;
alter table public.profiles add column if not exists viewers_positions  jsonb;
alter table public.profiles add column if not exists overlay_themes     jsonb;
alter table public.profiles add column if not exists premium_until      timestamptz;


-- ── 2. Trigger: cria perfil ao registrar novo usuário ────────

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id)
  values (new.id)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();


-- ── 3. Row Level Security (RLS) ──────────────────────────────
-- Cada usuário só pode ler/atualizar o próprio perfil.

alter table public.profiles enable row level security;

drop policy if exists "Usuário lê próprio perfil" on public.profiles;
create policy "Usuário lê próprio perfil"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "Usuário atualiza próprio perfil" on public.profiles;
create policy "Usuário atualiza próprio perfil"
  on public.profiles for update
  using (auth.uid() = id);


-- ── 4. Trigger: expira Premium automaticamente ───────────────
-- Dispara antes de qualquer UPDATE na tabela profiles.
-- Se premium_until já passou, zera is_premium e premium_until.

create or replace function public.check_premium_expiry()
returns trigger language plpgsql as $$
begin
  if NEW.is_premium = true
     and NEW.premium_until is not null
     and NEW.premium_until < now() then
    NEW.is_premium    = false;
    NEW.premium_until = null;
  end if;
  return NEW;
end;
$$;

drop trigger if exists trg_premium_expiry on public.profiles;
create trigger trg_premium_expiry
  before update on public.profiles
  for each row execute procedure public.check_premium_expiry();


-- ── 5. Função: ativar Premium por N dias ─────────────────────
-- Uso: select activate_premium('email@usuario.com');
--      select activate_premium('email@usuario.com', 60);

create or replace function public.activate_premium(user_email text, days int default 30)
returns void language plpgsql security definer as $$
begin
  update public.profiles
  set is_premium    = true,
      premium_until = now() + (days || ' days')::interval
  where id = (select id from auth.users where email = user_email);
end;
$$;


-- ── 6. Para marcar um usuário como premium (via SQL) ─────────
-- Ativa Premium por 30 dias para um usuário pelo e-mail:
--
--   update public.profiles
--   set is_premium = true,
--       premium_until = now() + interval '30 days'
--   where id = (select id from auth.users where email = 'email@do.usuario');
--
-- Para revogar:
--   update public.profiles
--   set is_premium = false, premium_until = null
--   where id = (select id from auth.users where email = 'email@do.usuario');
