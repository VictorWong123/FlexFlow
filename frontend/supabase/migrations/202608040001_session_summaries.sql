create table if not exists public.session_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_key uuid not null default gen_random_uuid(),
  schema_version integer not null default 1 check (schema_version > 0),
  summary_text text not null,
  pain_points text[] not null default '{}',
  stretches_performed text[] not null default '{}',
  youtube_links jsonb not null default '[]',
  duration_seconds integer not null default 0 check (duration_seconds >= 0),
  created_at timestamptz not null default now()
);

alter table public.session_summaries add column if not exists session_key uuid;
alter table public.session_summaries add column if not exists schema_version integer not null default 1;
update public.session_summaries set session_key = gen_random_uuid() where session_key is null;
alter table public.session_summaries alter column session_key set default gen_random_uuid();
alter table public.session_summaries alter column session_key set not null;

create unique index if not exists session_summaries_user_session_key
  on public.session_summaries (user_id, session_key);

grant select on table public.session_summaries to authenticated;
revoke insert, update, delete on table public.session_summaries from authenticated, anon;
revoke all on table public.session_summaries from anon;
alter table public.session_summaries enable row level security;

drop policy if exists "session_summaries_owner_select" on public.session_summaries;
create policy "session_summaries_owner_select" on public.session_summaries
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "session_summaries_owner_insert" on public.session_summaries;
drop policy if exists "session_summaries_owner_update" on public.session_summaries;
drop policy if exists "session_summaries_owner_delete" on public.session_summaries;

create table if not exists public.therapy_sessions (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  room_name text not null unique,
  status text not null default 'active'
    check (status in ('active', 'summarizing', 'completed', 'expired', 'failed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create unique index if not exists therapy_sessions_one_open_per_user
  on public.therapy_sessions (user_id)
  where status in ('active', 'summarizing');
create index if not exists therapy_sessions_user_created_at
  on public.therapy_sessions (user_id, created_at desc);

alter table public.therapy_sessions enable row level security;
grant select on table public.therapy_sessions to authenticated;
revoke insert, update, delete on table public.therapy_sessions from authenticated, anon;

drop policy if exists "therapy_sessions_owner_select" on public.therapy_sessions;
create policy "therapy_sessions_owner_select" on public.therapy_sessions
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "therapy_sessions_owner_insert" on public.therapy_sessions;
create policy "therapy_sessions_owner_insert" on public.therapy_sessions
  for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists "therapy_sessions_owner_update" on public.therapy_sessions;
create policy "therapy_sessions_owner_update" on public.therapy_sessions
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "therapy_sessions_owner_delete" on public.therapy_sessions;
create policy "therapy_sessions_owner_delete" on public.therapy_sessions
  for delete to authenticated using ((select auth.uid()) = user_id);

create or replace function public.issue_therapy_session(
  p_session_id uuid,
  p_room_name text,
  p_expires_at timestamptz
) returns table(id uuid, room_name text, status text, expires_at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare recent_count integer; caller_id uuid := (select auth.uid());
begin
  if caller_id is null then raise exception 'unauthorized'; end if;
  if p_room_name <> 'flexflow-' || p_session_id::text
     or p_expires_at <= now() or p_expires_at > now() + interval '2 hours 1 minute' then
    raise exception 'invalid_session';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(caller_id::text, 0));
  update public.therapy_sessions s set status = 'expired', updated_at = now()
    where s.user_id = caller_id and s.status in ('active', 'summarizing') and s.expires_at <= now();
  return query select s.id, s.room_name, s.status, s.expires_at
    from public.therapy_sessions s
    where s.user_id = caller_id and s.status = 'active' and s.expires_at > now()
    order by s.created_at desc limit 1;
  if found then return; end if;
  if exists (select 1 from public.therapy_sessions s where s.user_id = caller_id and s.status = 'summarizing') then
    raise exception 'session_in_progress';
  end if;
  select count(*) into recent_count from public.therapy_sessions s
    where s.user_id = caller_id and s.created_at >= now() - interval '1 hour';
  if recent_count >= 10 then raise exception 'session_quota_exceeded'; end if;
  insert into public.therapy_sessions(id, user_id, room_name, expires_at)
    values (p_session_id, caller_id, p_room_name, p_expires_at);
  return query select p_session_id, p_room_name, 'active'::text, p_expires_at;
end $$;

create or replace function public.delete_session_summary(p_summary_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare caller_id uuid := (select auth.uid());
begin
  if caller_id is null then raise exception 'unauthorized'; end if;
  delete from public.session_summaries where id = p_summary_id and user_id = caller_id;
  return found;
end $$;

create or replace function public.claim_therapy_session(p_session_id uuid)
returns text language plpgsql security definer set search_path = '' as $$
declare current_status text; current_expiry timestamptz; caller_id uuid := (select auth.uid());
begin
  if caller_id is null then raise exception 'unauthorized'; end if;
  select s.status, s.expires_at into current_status, current_expiry
    from public.therapy_sessions s where s.id = p_session_id and s.user_id = caller_id for update;
  if not found then return 'not_found'; end if;
  if current_status = 'completed' then return 'completed'; end if;
  if current_expiry <= now() then
    update public.therapy_sessions set status = 'expired', updated_at = now() where id = p_session_id;
    return 'expired';
  end if;
  if current_status = 'summarizing' then return 'in_progress'; end if;
  if current_status <> 'active' then return current_status; end if;
  update public.therapy_sessions set status = 'summarizing', updated_at = now() where id = p_session_id;
  return 'claimed';
end $$;

create or replace function public.complete_therapy_session(
  p_session_id uuid, p_summary_text text, p_pain_points text[],
  p_stretches_performed text[], p_youtube_links jsonb, p_duration_seconds integer
) returns uuid language plpgsql security definer set search_path = '' as $$
declare summary_id uuid; caller_id uuid := (select auth.uid());
begin
  if caller_id is null then raise exception 'unauthorized'; end if;
  if p_summary_text is null or char_length(p_summary_text) < 1 or char_length(p_summary_text) > 2000
     or coalesce(array_length(p_pain_points, 1), 0) > 10
     or coalesce(array_length(p_stretches_performed, 1), 0) > 20
     or exists (select 1 from unnest(p_pain_points) item where item is null or char_length(item) > 200)
     or exists (select 1 from unnest(p_stretches_performed) item where item is null or char_length(item) > 200)
     or p_duration_seconds < 0 or p_duration_seconds > 28800
     or case when jsonb_typeof(p_youtube_links) = 'array' then jsonb_array_length(p_youtube_links) > 3 else true end
     or exists (
       select 1 from jsonb_array_elements(case when jsonb_typeof(p_youtube_links) = 'array' then p_youtube_links else '[]'::jsonb end) link
       where jsonb_typeof(link) <> 'object'
          or jsonb_typeof(link->'label') <> 'string'
          or jsonb_typeof(link->'url') <> 'string'
          or char_length(link->>'label') > 200
          or char_length(link->>'url') > 500
     ) then
    raise exception 'invalid_summary';
  end if;
  if not exists (select 1 from public.therapy_sessions s where s.id = p_session_id and s.user_id = caller_id and s.status = 'summarizing' for update) then
    raise exception 'session_not_claimed';
  end if;
  insert into public.session_summaries(user_id, session_key, schema_version, summary_text, pain_points, stretches_performed, youtube_links, duration_seconds)
    values (caller_id, p_session_id, 1, p_summary_text, p_pain_points, p_stretches_performed, p_youtube_links, p_duration_seconds)
    on conflict (user_id, session_key) do update set
      summary_text = excluded.summary_text, pain_points = excluded.pain_points,
      stretches_performed = excluded.stretches_performed, youtube_links = excluded.youtube_links,
      duration_seconds = excluded.duration_seconds
    returning id into summary_id;
  update public.therapy_sessions set status = 'completed', updated_at = now() where id = p_session_id;
  return summary_id;
end $$;

create or replace function public.close_therapy_session(p_session_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare caller_id uuid := (select auth.uid());
begin
  if caller_id is null then raise exception 'unauthorized'; end if;
  update public.therapy_sessions set status = 'completed', updated_at = now()
    where id = p_session_id and user_id = caller_id and status in ('active', 'summarizing');
  return found;
end $$;

create or replace function public.release_therapy_session(p_session_id uuid, p_failed boolean)
returns boolean language plpgsql security definer set search_path = '' as $$
declare caller_id uuid := (select auth.uid());
begin
  if caller_id is null then raise exception 'unauthorized'; end if;
  update public.therapy_sessions
    set status = case when p_failed or expires_at <= now() then 'failed' else 'active' end, updated_at = now()
    where id = p_session_id and user_id = caller_id and status = 'summarizing';
  return found;
end $$;

revoke all on function public.issue_therapy_session(uuid, text, timestamptz) from public, anon;
revoke all on function public.claim_therapy_session(uuid) from public, anon;
revoke all on function public.complete_therapy_session(uuid, text, text[], text[], jsonb, integer) from public, anon;
revoke all on function public.close_therapy_session(uuid) from public, anon;
revoke all on function public.release_therapy_session(uuid, boolean) from public, anon;
revoke all on function public.delete_session_summary(uuid) from public, anon;
grant execute on function public.issue_therapy_session(uuid, text, timestamptz) to authenticated;
grant execute on function public.claim_therapy_session(uuid) to authenticated;
grant execute on function public.complete_therapy_session(uuid, text, text[], text[], jsonb, integer) to authenticated;
grant execute on function public.close_therapy_session(uuid) to authenticated;
grant execute on function public.release_therapy_session(uuid, boolean) to authenticated;
grant execute on function public.delete_session_summary(uuid) to authenticated;
