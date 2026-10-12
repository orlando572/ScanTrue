-- Una sola entrada de texto. Aplicar después de 004 con la API local detenida.
-- Un título histórico no se puede descartar sin una decisión de conservación.
do $$
begin
    if exists (select 1 from public.analisis where titulo is not null) then
        raise exception 'Existen títulos históricos; conservarlos antes de retirar la columna';
    end if;
end;
$$;

create function public.crear_analisis_texto_unico(
    p_usuario_id uuid,
    p_url text,
    p_texto text,
    p_hash_texto text,
    p_comparacion text,
    p_resultados jsonb,
    p_resultado_unificado jsonb
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

    insert into public.analisis
        (usuario_id, url, texto, hash_texto, comparacion, resultado_unificado)
    values
        (p_usuario_id, p_url, p_texto, p_hash_texto, p_comparacion,
         p_resultado_unificado)
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

revoke execute on function public.crear_analisis_texto_unico(
    uuid, text, text, text, text, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.crear_analisis_texto_unico(
    uuid, text, text, text, text, jsonb, jsonb
) to service_role;

drop function public.crear_analisis_completo(
    uuid, text, text, text, text, text, jsonb, jsonb
);
drop function public.crear_analisis_servidor(
    uuid, text, text, text, text, jsonb
);
alter table public.analisis drop column titulo;

notify pgrst, 'reload schema';
