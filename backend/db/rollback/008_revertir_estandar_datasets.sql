-- Deshace backend/db/migrations/008_estandar_datasets.sql.
-- Las versiones y sus filas se conservan: los datos de cada fragmento siguen en
-- procedencia.fragmento; se pierden los manifiestos.
-- Antes de ejecutarlo, volver a una versión del backend anterior a la 008.

drop function if exists public.crear_version_dataset(text, text, uuid, jsonb, jsonb, jsonb);

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

alter table public.datasets_version drop column if exists manifiesto;

drop index if exists public.dataset_items_fragmento_idx;

alter table public.dataset_items
    drop column if exists tokens_bilstm,
    drop column if exists peso,
    drop column if exists fuente,
    drop column if exists id_fragmento;
