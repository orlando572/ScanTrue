-- Identidad e historial de ScanTrue. Ejecutar una sola vez en el proyecto Supabase.
create table public.analisis (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null references auth.users(id) on delete cascade,
    fecha timestamptz not null default now(),
    titulo text check (titulo is null or char_length(titulo) <= 200),
    url text check (url is null or char_length(url) <= 2048),
    hash_texto text not null check (hash_texto ~ '^[0-9a-f]{64}$'),
    comparacion text not null check (comparacion in ('coinciden', 'discrepan', 'no_disponible')),
    estado_blockchain text not null default 'no_iniciado'
        check (estado_blockchain in ('no_iniciado', 'pendiente', 'confirmado', 'fallido')),
    hash_transaccion text check (hash_transaccion is null or hash_transaccion ~ '^0x[0-9a-fA-F]{64}$')
);

create table public.resultados_modelo (
    id uuid primary key default gen_random_uuid(),
    analisis_id uuid not null references public.analisis(id) on delete cascade,
    modelo text not null check (modelo in ('bilstm', 'mbert')),
    version text not null check (char_length(version) between 1 and 160),
    clase text not null check (clase in ('falsa', 'real')),
    probabilidad_falsa double precision not null
        check (probabilidad_falsa >= 0 and probabilidad_falsa <= 1),
    tokens_leidos integer not null check (tokens_leidos > 0),
    unique (analisis_id, modelo)
);

create index analisis_usuario_fecha_idx
    on public.analisis (usuario_id, fecha desc, id desc);
create index resultados_modelo_analisis_idx
    on public.resultados_modelo (analisis_id);

alter table public.analisis enable row level security;
alter table public.resultados_modelo enable row level security;

revoke all on public.analisis from anon, authenticated;
revoke all on public.resultados_modelo from anon, authenticated;
grant select, insert, delete on public.analisis to authenticated;
grant select, insert on public.resultados_modelo to authenticated;

create policy analisis_leer_propio on public.analisis for select
    to authenticated using (usuario_id = (select auth.uid()));
create policy analisis_crear_propio on public.analisis for insert
    to authenticated with check (usuario_id = (select auth.uid()));
create policy analisis_eliminar_propio on public.analisis for delete
    to authenticated using (usuario_id = (select auth.uid()));

create policy resultados_leer_propios on public.resultados_modelo for select
    to authenticated using (
        exists (
            select 1 from public.analisis a
            where a.id = analisis_id and a.usuario_id = (select auth.uid())
        )
    );
create policy resultados_crear_propios on public.resultados_modelo for insert
    to authenticated with check (
        exists (
            select 1 from public.analisis a
            where a.id = analisis_id and a.usuario_id = (select auth.uid())
        )
    );

-- Una función invocadora reúne el análisis y sus predicciones en una transacción.
create function public.crear_analisis(
    p_titulo text,
    p_url text,
    p_hash_texto text,
    p_comparacion text,
    p_resultados jsonb
) returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_usuario_id uuid := (select auth.uid());
    v_analisis_id uuid;
    v_resultado jsonb;
begin
    if v_usuario_id is null then
        raise exception 'Se requiere una sesión de usuario' using errcode = '42501';
    end if;
    if jsonb_typeof(p_resultados) is distinct from 'array'
       or jsonb_array_length(p_resultados) not between 1 and 2 then
        raise exception 'Se requiere una o dos predicciones reales' using errcode = '22023';
    end if;

    insert into public.analisis
        (usuario_id, titulo, url, hash_texto, comparacion)
    values
        (v_usuario_id, p_titulo, p_url, p_hash_texto, p_comparacion)
    returning id into v_analisis_id;

    for v_resultado in select value from jsonb_array_elements(p_resultados) loop
        insert into public.resultados_modelo
            (analisis_id, modelo, version, clase, probabilidad_falsa, tokens_leidos)
        values (
            v_analisis_id,
            v_resultado->>'modelo',
            v_resultado->>'version',
            v_resultado->>'clase',
            (v_resultado->>'probabilidad_falsa')::double precision,
            (v_resultado->>'tokens_leidos')::integer
        );
    end loop;
    return v_analisis_id;
end;
$$;

revoke execute on function public.crear_analisis(text, text, text, text, jsonb)
    from public, anon;
grant execute on function public.crear_analisis(text, text, text, text, jsonb)
    to authenticated;
