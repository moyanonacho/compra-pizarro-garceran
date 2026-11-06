-- Lista de la compra Familia Pizarro Garcerán: tablas, seguridad y fotos.
-- Solo los usuarios apuntados en "members" (la cuenta familiar) pueden leer y escribir.

create table if not exists public.members (user_id uuid primary key references auth.users(id) on delete cascade);
alter table public.members enable row level security;

create table if not exists public.docs (
  col text not null,
  id text not null,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (col, id)
);
alter table public.docs enable row level security;
alter table public.docs replica identity full;

create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public
as $$ select exists (select 1 from public.members where user_id = auth.uid()) $$;

drop policy if exists "familia lee y escribe" on public.docs;
create policy "familia lee y escribe" on public.docs for all to authenticated
  using (public.is_member()) with check (public.is_member());

drop policy if exists "cada uno se ve" on public.members;
create policy "cada uno se ve" on public.members for select to authenticated using (user_id = auth.uid());

-- mezcla recursiva de objetos (como "update" de la app original)
create or replace function public.jsonb_deep_merge(a jsonb, b jsonb) returns jsonb
language sql immutable as $$
  select case
    when jsonb_typeof(a) = 'object' and jsonb_typeof(b) = 'object' then
      coalesce((select jsonb_object_agg(k,
          case when a ? k and b ? k then public.jsonb_deep_merge(a -> k, b -> k)
               when b ? k then b -> k else a -> k end)
        from (select jsonb_object_keys(a) k union select jsonb_object_keys(b)) ks), '{}'::jsonb)
    else b end
$$;

create or replace function public.doc_update(p_col text, p_id text, p_patch jsonb) returns void
language plpgsql security invoker set search_path = public
as $$
begin
  update public.docs set data = public.jsonb_deep_merge(data, p_patch), updated_at = now()
   where col = p_col and id = p_id;
  if not found then raise exception 'no existe %/%', p_col, p_id using errcode = 'P0002'; end if;
end $$;

-- avisos en tiempo real a los móviles abiertos
do $$ begin
  alter publication supabase_realtime add table public.docs;
exception when duplicate_object then null; end $$;

-- fotos: carpeta pública (nombres aleatorios); solo la familia sube y borra
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('fotos', 'fotos', true, 10485760, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = true;

drop policy if exists "familia sube fotos" on storage.objects;
create policy "familia sube fotos" on storage.objects for insert to authenticated
  with check (bucket_id = 'fotos' and public.is_member());
drop policy if exists "familia borra fotos" on storage.objects;
create policy "familia borra fotos" on storage.objects for delete to authenticated
  using (bucket_id = 'fotos' and public.is_member());

-- catálogos (los sube el robot mensual de GitHub; usuario robot.catalogo@example.com)

insert into storage.buckets (id,name,public) values ('catalogo','catalogo',true) on conflict (id) do update set public=true;
drop policy if exists "robot catalogo" on storage.objects;
create policy "robot catalogo" on storage.objects for all to authenticated
  using (bucket_id='catalogo' and auth.uid()='<id del robot>'::uuid) with check (bucket_id='catalogo' and auth.uid()='<id del robot>'::uuid);
