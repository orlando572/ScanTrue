-- Contrato de historial y resultado unificado. Aplicar después de 003.
-- Los registros anteriores conservan texto NULL; el valor unificado se reconstruye
-- únicamente desde las predicciones reales que ya quedaron guardadas.
alter table public.analisis
    add column texto text,
    add column resultado_unificado jsonb
        check (resultado_unificado is null or jsonb_typeof(resultado_unificado) = 'object');

with resultados_previos as (
    select analisis_id,
           max(probabilidad_falsa) filter (where modelo = 'bilstm') as bilstm,
           max(probabilidad_falsa) filter (where modelo = 'mbert') as mbert
    from public.resultados_modelo
    group by analisis_id
)
update public.analisis as a
set resultado_unificado = jsonb_build_object(
    'probabilidad_falsa',
    case
        when p.bilstm is not null and p.mbert is not null
            then least(1.0, greatest(0.0, 0.3 * p.bilstm + 0.7 * p.mbert))
        else coalesce(p.bilstm, p.mbert)
    end,
    'modelos_utilizados',
    case
        when p.bilstm is not null and p.mbert is not null
            then jsonb_build_array('bilstm', 'mbert')
        when p.bilstm is not null then jsonb_build_array('bilstm')
        else jsonb_build_array('mbert')
    end,
    'pesos_aplicados', jsonb_build_object(
        'bilstm', case when p.mbert is null then 1.0 when p.bilstm is null then 0.0 else 0.3 end,
        'mbert', case when p.bilstm is null then 1.0 when p.mbert is null then 0.0 else 0.7 end
    ),
    'version_regla', 'media_ponderada_v1'
)
from resultados_previos as p
where a.id = p.analisis_id
  and (p.bilstm is not null or p.mbert is not null)
  and a.resultado_unificado is null;

-- La función nueva conserva la operación atómica y la autorización del backend.
-- La función anterior permanece para procesos anteriores durante el despliegue.
create function public.crear_analisis_completo(
    p_usuario_id uuid,
    p_titulo text,
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
        (usuario_id, titulo, url, texto, hash_texto, comparacion, resultado_unificado)
    values
        (p_usuario_id, p_titulo, p_url, p_texto, p_hash_texto, p_comparacion,
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

revoke execute on function public.crear_analisis_completo(
    uuid, text, text, text, text, text, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.crear_analisis_completo(
    uuid, text, text, text, text, text, jsonb, jsonb
) to service_role;

notify pgrst, 'reload schema';
