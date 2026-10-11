-- Solo el backend, con clave secreta, puede crear predicciones persistidas.
revoke insert on public.analisis from authenticated;
revoke insert on public.resultados_modelo from authenticated;

drop policy analisis_crear_propio on public.analisis;
drop policy resultados_crear_propios on public.resultados_modelo;

drop function public.crear_analisis(text, text, text, text, jsonb);

create function public.crear_analisis_servidor(
    p_usuario_id uuid,
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
    v_analisis_id uuid;
    v_resultado jsonb;
begin
    if p_usuario_id is null then
        raise exception 'Se requiere un propietario' using errcode = '22023';
    end if;
    if jsonb_typeof(p_resultados) is distinct from 'array'
       or jsonb_array_length(p_resultados) not between 1 and 2 then
        raise exception 'Se requiere una o dos predicciones reales' using errcode = '22023';
    end if;

    insert into public.analisis
        (usuario_id, titulo, url, hash_texto, comparacion)
    values
        (p_usuario_id, p_titulo, p_url, p_hash_texto, p_comparacion)
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

revoke execute on function public.crear_analisis_servidor(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.crear_analisis_servidor(uuid, text, text, text, text, jsonb)
    to service_role;
