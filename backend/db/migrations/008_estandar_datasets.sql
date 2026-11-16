-- Estándar de datasets (datos_comunes/estandar.py): cada fila de una versión es un
-- fragmento de 100–200 tokens con las columnas de comun_v1, y cada versión guarda un
-- manifiesto con los SHA-256 de su contenido y del código que la construyó.
-- Aplicar después de 007. Las versiones creadas antes del estándar (una fila por noticia)
-- se conservan con estas columnas vacías; no se pueden exportar para entrenar.

alter table public.dataset_items
    add column id_fragmento text,
    add column fuente text,
    add column peso double precision check (peso is null or (peso > 0 and peso <= 1)),
    add column tokens_bilstm integer check (tokens_bilstm is null or tokens_bilstm > 0);

-- Las versiones creadas entre la 007 y esta migración guardaban el fragmento en la procedencia.
update public.dataset_items
set id_fragmento = procedencia->'fragmento'->>'id_fragmento',
    fuente = coalesce(procedencia->>'fuente', 'panel'),
    peso = (procedencia->'fragmento'->>'peso')::double precision,
    tokens_bilstm = (procedencia->'fragmento'->>'tokens_bilstm')::integer
where procedencia ? 'fragmento';

create unique index dataset_items_fragmento_idx
    on public.dataset_items (version_id, id_fragmento)
    where id_fragmento is not null;

alter table public.datasets_version
    add column manifiesto jsonb not null default '{}'::jsonb
        check (jsonb_typeof(manifiesto) = 'object');

-- La función de la 007 no conoce las columnas nuevas: se sustituye.
drop function if exists public.crear_version_dataset(text, text, uuid, jsonb, jsonb);

create function public.crear_version_dataset(
    p_nombre text,
    p_descripcion text,
    p_creado_por uuid,
    p_resumen jsonb,
    p_manifiesto jsonb,
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
        raise exception 'La versión necesita al menos un fragmento' using errcode = '22023';
    end if;

    insert into public.datasets_version (nombre, descripcion, creado_por, resumen, manifiesto)
    values (p_nombre, p_descripcion, p_creado_por, coalesce(p_resumen, '{}'::jsonb),
            coalesce(p_manifiesto, '{}'::jsonb))
    returning id into v_version_id;

    insert into public.dataset_items
        (version_id, analisis_id, texto, hash_texto, etiqueta, particion, grupo,
         url, dominio, decision, procedencia, evidencia,
         id_fragmento, fuente, peso, tokens_bilstm)
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
           coalesce(item->'evidencia', '[]'::jsonb),
           item->>'id_fragmento',
           item->>'fuente',
           (item->>'peso')::double precision,
           (item->>'tokens_bilstm')::integer
    from jsonb_array_elements(p_items) as item;

    return v_version_id;
end;
$$;

revoke execute on function public.crear_version_dataset(text, text, uuid, jsonb, jsonb, jsonb)
    from public, anon, authenticated;
grant execute on function public.crear_version_dataset(text, text, uuid, jsonb, jsonb, jsonb)
    to service_role;
