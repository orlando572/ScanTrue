-- Plataforma web (incrementos 1 y 3): fragmentos, texto por modelo, revisión,
-- versiones de dataset y hueco de la verificación web (incremento 2).
-- Aplicar después de 006. El backend lee y escribe todo con la clave secreta
-- (service_role); las tablas nuevas tienen RLS sin políticas, así que desde el
-- navegador no se puede leer nada directamente.

create extension if not exists pg_trgm with schema extensions;

-- ── Análisis: fragmento original, fragmentos separados y datos para filtrar ──
alter table public.analisis
    add column texto_original text
        check (texto_original is null or char_length(texto_original) <= 20000),
    add column fragmentos jsonb
        check (fragmentos is null or jsonb_typeof(fragmentos) = 'array'),
    add column texto_recortado boolean not null default false,
    add column dominio text generated always as (
        lower(substring(url from '^[A-Za-z][A-Za-z0-9+.-]*://(?:[^/?#@]*@)?(?:www\.)?([^/:?#]+)'))
    ) stored,
    add column discrepa boolean generated always as (comparacion = 'discrepan') stored;

-- Texto recortado que recibió cada modelo (cada uno lee un prefijo distinto).
alter table public.resultados_modelo
    add column texto_modelo text;

create index analisis_probabilidad_idx on public.analisis (probabilidad_unificada);
create index analisis_dominio_idx on public.analisis (dominio) where dominio is not null;
create index analisis_prioridad_idx on public.analisis (discrepa desc, fecha desc, id desc);
create index analisis_texto_trgm_idx
    on public.analisis using gin (texto extensions.gin_trgm_ops);

-- ── Verificación web (incremento 2): queda vacía hasta que exista la cola ──
create table public.verificaciones_web (
    analisis_id uuid primary key references public.analisis(id) on delete cascade,
    estado text not null default 'pendiente'
        check (estado in ('pendiente', 'en_proceso', 'completada', 'fallida')),
    conclusion text
        check (conclusion is null or conclusion in
               ('respaldada', 'contradicha', 'fuera_de_contexto', 'evidencia_insuficiente')),
    resumen text check (resumen is null or char_length(resumen) <= 4000),
    afirmaciones jsonb not null default '[]'::jsonb
        check (jsonb_typeof(afirmaciones) = 'array'),
    fuentes jsonb not null default '[]'::jsonb
        check (jsonb_typeof(fuentes) = 'array'),
    modelo_llm text,
    creado_en timestamptz not null default now(),
    actualizado_en timestamptz not null default now(),
    check ((estado = 'completada') = (conclusion is not null))
);

-- ── Revisión del administrador (incremento 3) ──
create table public.revisiones (
    analisis_id uuid primary key references public.analisis(id) on delete cascade,
    decision text not null check (decision in ('aprobado', 'corregido', 'descartado')),
    etiqueta_final text check (etiqueta_final is null or etiqueta_final in ('falsa', 'real')),
    nota text check (nota is null or char_length(nota) <= 2000),
    evidencia jsonb not null default '[]'::jsonb check (jsonb_typeof(evidencia) = 'array'),
    grupo_evento text check (grupo_evento is null or char_length(grupo_evento) <= 120),
    revisor_id uuid references auth.users(id) on delete set null,
    fecha timestamptz not null default now(),
    -- Un caso descartado no tiene etiqueta; uno aprobado o corregido, sí.
    check ((decision = 'descartado') = (etiqueta_final is null))
);

create index revisiones_decision_idx on public.revisiones (decision);

-- ── Versiones de dataset: copia de cada caso aprobado, con procedencia ──
create table public.datasets_version (
    id uuid primary key default gen_random_uuid(),
    nombre text not null unique check (char_length(nombre) between 1 and 80),
    descripcion text check (descripcion is null or char_length(descripcion) <= 500),
    creado_por uuid references auth.users(id) on delete set null,
    fecha timestamptz not null default now(),
    resumen jsonb not null default '{}'::jsonb check (jsonb_typeof(resumen) = 'object')
);

create table public.dataset_items (
    id uuid primary key default gen_random_uuid(),
    version_id uuid not null references public.datasets_version(id) on delete cascade,
    -- Si el propietario borra su análisis, la fila del dataset conserva su copia.
    analisis_id uuid references public.analisis(id) on delete set null,
    texto text not null,
    hash_texto text not null,
    etiqueta text not null check (etiqueta in ('falsa', 'real')),
    particion text not null check (particion in ('entrenamiento', 'prueba')),
    grupo text not null,
    url text,
    dominio text,
    decision text not null check (decision in ('aprobado', 'corregido')),
    procedencia jsonb not null default '{}'::jsonb,
    evidencia jsonb not null default '[]'::jsonb
);

create index dataset_items_version_idx on public.dataset_items (version_id, particion);

alter table public.verificaciones_web enable row level security;
alter table public.revisiones enable row level security;
alter table public.datasets_version enable row level security;
alter table public.dataset_items enable row level security;

revoke all on public.verificaciones_web, public.revisiones,
              public.datasets_version, public.dataset_items
    from anon, authenticated;
grant select, insert, update, delete
    on public.verificaciones_web, public.revisiones,
       public.datasets_version, public.dataset_items
    to service_role;

-- ── Creación del análisis con fragmentos y texto por modelo ──
-- La función anterior (crear_analisis_texto_unico) se conserva durante el despliegue.
create function public.crear_analisis_con_fragmentos(
    p_usuario_id uuid,
    p_url text,
    p_texto text,
    p_hash_texto text,
    p_comparacion text,
    p_resultados jsonb,
    p_resultado_unificado jsonb,
    p_texto_original text,
    p_fragmentos jsonb,
    p_texto_recortado boolean
) returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_analisis_id uuid;
    v_resultado jsonb;
begin
    if p_usuario_id is null or p_texto is null or btrim(p_texto) = '' then
        raise exception 'Se requieren propietario y texto' using errcode = '22023';
    end if;
    if jsonb_typeof(p_resultados) is distinct from 'array'
       or jsonb_array_length(p_resultados) not between 1 and 2 then
        raise exception 'Se requiere una o dos predicciones reales' using errcode = '22023';
    end if;
    if jsonb_typeof(p_resultado_unificado) is distinct from 'object'
       or p_resultado_unificado->>'version_regla' is distinct from 'media_ponderada_v1'
       or jsonb_typeof(p_resultado_unificado->'modelos_utilizados') is distinct from 'array'
       or jsonb_typeof(p_resultado_unificado->'pesos_aplicados') is distinct from 'object'
       or (p_resultado_unificado->>'probabilidad_falsa') is null
       or (p_resultado_unificado->>'probabilidad_falsa')::double precision not between 0 and 1 then
        raise exception 'Resultado unificado inválido' using errcode = '22023';
    end if;
    if p_fragmentos is not null and jsonb_typeof(p_fragmentos) is distinct from 'array' then
        raise exception 'Los fragmentos deben ser una lista' using errcode = '22023';
    end if;

    insert into public.analisis
        (usuario_id, url, texto, hash_texto, comparacion, resultado_unificado,
         texto_original, fragmentos, texto_recortado)
    values
        (p_usuario_id, p_url, p_texto, p_hash_texto, p_comparacion, p_resultado_unificado,
         p_texto_original, p_fragmentos, coalesce(p_texto_recortado, false))
    returning id into v_analisis_id;

    for v_resultado in select value from jsonb_array_elements(p_resultados) loop
        insert into public.resultados_modelo
            (analisis_id, modelo, version, clase, probabilidad_falsa, tokens_leidos, texto_modelo)
        values (
            v_analisis_id,
            v_resultado->>'modelo',
            v_resultado->>'version',
            v_resultado->>'clase',
            (v_resultado->>'probabilidad_falsa')::double precision,
            (v_resultado->>'tokens_leidos')::integer,
            v_resultado->>'texto_modelo'
        );
    end loop;
    return v_analisis_id;
end;
$$;

revoke execute on function public.crear_analisis_con_fragmentos(
    uuid, text, text, text, text, jsonb, jsonb, text, jsonb, boolean
) from public, anon, authenticated;
grant execute on function public.crear_analisis_con_fragmentos(
    uuid, text, text, text, text, jsonb, jsonb, text, jsonb, boolean
) to service_role;

-- ── Versión de dataset y sus filas, en una sola transacción ──
create function public.crear_version_dataset(
    p_nombre text,
    p_descripcion text,
    p_creado_por uuid,
    p_resumen jsonb,
    p_items jsonb
) returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_version_id uuid;
begin
    if jsonb_typeof(p_items) is distinct from 'array' or jsonb_array_length(p_items) = 0 then
        raise exception 'La versión necesita al menos un caso' using errcode = '22023';
    end if;

    insert into public.datasets_version (nombre, descripcion, creado_por, resumen)
    values (p_nombre, p_descripcion, p_creado_por, coalesce(p_resumen, '{}'::jsonb))
    returning id into v_version_id;

    insert into public.dataset_items
        (version_id, analisis_id, texto, hash_texto, etiqueta, particion, grupo,
         url, dominio, decision, procedencia, evidencia)
    select v_version_id,
           (item->>'analisis_id')::uuid,
           item->>'texto',
           item->>'hash_texto',
           item->>'etiqueta',
           item->>'particion',
           item->>'grupo',
           item->>'url',
           item->>'dominio',
           item->>'decision',
           coalesce(item->'procedencia', '{}'::jsonb),
           coalesce(item->'evidencia', '[]'::jsonb)
    from jsonb_array_elements(p_items) as item;

    return v_version_id;
end;
$$;

revoke execute on function public.crear_version_dataset(text, text, uuid, jsonb, jsonb)
    from public, anon, authenticated;
grant execute on function public.crear_version_dataset(text, text, uuid, jsonb, jsonb)
    to service_role;

-- ── Resumen para la portada (solo visibles) y para el panel (todos) ──
-- Los cortes de nivel son los de frontend/src/popup/result-presentation.js:
-- porcentaje redondeado ≤ 20, 40, 60, 80 y 100.
create function public.resumen_plataforma(p_solo_visibles boolean default false)
returns jsonb
language sql
stable
set search_path = ''
as $$
    with casos as (
        select a.*
        from public.analisis as a
        where not p_solo_visibles or not a.oculto
    )
    select jsonb_build_object(
        'total', count(*),
        'ocultos', count(*) filter (where c.oculto),
        'ultimas_24h', count(*) filter (where c.fecha >= now() - interval '24 hours'),
        'ultimos_7_dias', count(*) filter (where c.fecha >= now() - interval '7 days'),
        'probabilidad_media', avg(c.probabilidad_unificada),
        'niveles', jsonb_build_array(
            count(*) filter (where c.probabilidad_unificada < 0.205),
            count(*) filter (where c.probabilidad_unificada >= 0.205 and c.probabilidad_unificada < 0.405),
            count(*) filter (where c.probabilidad_unificada >= 0.405 and c.probabilidad_unificada < 0.605),
            count(*) filter (where c.probabilidad_unificada >= 0.605 and c.probabilidad_unificada < 0.805),
            count(*) filter (where c.probabilidad_unificada >= 0.805)
        ),
        'comparacion', jsonb_build_object(
            'coinciden', count(*) filter (where c.comparacion = 'coinciden'),
            'discrepan', count(*) filter (where c.comparacion = 'discrepan'),
            'no_disponible', count(*) filter (where c.comparacion = 'no_disponible')
        ),
        'blockchain', jsonb_build_object(
            'confirmado', count(*) filter (where c.estado_blockchain = 'confirmado'),
            'pendiente', count(*) filter (where c.estado_blockchain in ('pendiente', 'no_iniciado')),
            'fallido', count(*) filter (where c.estado_blockchain = 'fallido')
        ),
        'revisiones', jsonb_build_object(
            'aprobado', count(*) filter (where r.decision = 'aprobado'),
            'corregido', count(*) filter (where r.decision = 'corregido'),
            'descartado', count(*) filter (where r.decision = 'descartado'),
            'pendiente', count(*) filter (where r.analisis_id is null),
            'discrepan_pendientes', count(*) filter (where r.analisis_id is null and c.discrepa)
        ),
        'verificaciones_web', count(*) filter (where v.estado = 'completada'),
        'por_dia', coalesce((
            select jsonb_agg(jsonb_build_object('dia', d.dia, 'n', d.n) order by d.dia)
            from (
                select (x.fecha at time zone 'America/Lima')::date as dia, count(*) as n
                from casos as x
                where x.fecha >= now() - interval '30 days'
                group by 1
            ) as d
        ), '[]'::jsonb),
        'dominios', coalesce((
            select jsonb_agg(jsonb_build_object('dominio', t.dominio, 'n', t.n) order by t.n desc, t.dominio)
            from (
                select x.dominio, count(*) as n
                from casos as x
                where x.dominio is not null
                group by x.dominio
                order by count(*) desc, x.dominio
                limit 12
            ) as t
        ), '[]'::jsonb),
        'datasets', (select count(*) from public.datasets_version)
    )
    from casos as c
    left join public.revisiones as r on r.analisis_id = c.id
    left join public.verificaciones_web as v on v.analisis_id = c.id;
$$;

revoke execute on function public.resumen_plataforma(boolean) from public, anon, authenticated;
grant execute on function public.resumen_plataforma(boolean) to service_role;

notify pgrst, 'reload schema';
