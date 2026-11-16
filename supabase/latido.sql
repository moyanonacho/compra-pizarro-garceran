-- «Latido»: una escritura real en la base de datos que hace GitHub cada día para que Supabase no pause el proyecto.
-- Cualquiera puede llamarla, pero solo actualiza la hora del último latido.
create table if not exists public.latido (id int primary key default 1 check (id = 1), at timestamptz not null default now(), n bigint not null default 0);
alter table public.latido enable row level security;
insert into public.latido (id) values (1) on conflict do nothing;
create or replace function public.latido() returns timestamptz
language sql security definer set search_path = public
as $$ update public.latido set at = now(), n = n + 1 where id = 1 returning at $$;
revoke all on function public.latido() from public;
grant execute on function public.latido() to anon, authenticated;
