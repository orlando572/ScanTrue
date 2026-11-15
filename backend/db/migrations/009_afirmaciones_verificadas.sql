-- Búsqueda y guardado de la base de afirmaciones ya verificadas (incremento 2, Fase 3).
-- Aplicar después de 008, que creó la tabla afirmaciones_verificadas. Solo el backend, con la
-- clave secreta (service_role), usa estas funciones.

-- ── Buscar: exacta por hash y, si no hay, por similitud de trigramas ──
-- Solo devuelve afirmaciones que no han expirado (D5). Si hay coincidencia exacta, devuelve
-- solo esa. Si no, devuelve hasta p_limite candidatas parecidas, de mayor a menor similitud;
-- el backend decide cuál aceptar con sus comprobaciones (mismas cifras y misma negación).
-- p_umbral nunca baja de 0,3, el mínimo del operador % de pg_trgm.
create function public.buscar_afirmacion_verificada(
    p_hash_texto text,
    p_texto_normalizado text,
    p_umbral real default 0.8,
    p_limite integer default 5
)
returns table (
    id uuid,
    texto text,
    veredicto text,
    fuentes jsonb,
    modelo_llm text,
    version_prompts text,
    verificado_en timestamptz,
    expira_en timestamptz,
    similitud real,
    exacta boolean
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
begin
    return query
    select a.id, a.texto, a.veredicto, a.fuentes, a.modelo_llm, a.version_prompts,
           a.verificado_en, a.expira_en, 1.0::real, true
    from public.afirmaciones_verificadas as a
    where a.hash_texto = p_hash_texto
      and a.expira_en > now();
    if found then
        return;
    end if;

    return query
    select a.id, a.texto, a.veredicto, a.fuentes, a.modelo_llm, a.version_prompts,
           a.verificado_en, a.expira_en,
           extensions.similarity(a.texto_normalizado, p_texto_normalizado), false
    from public.afirmaciones_verificadas as a
    where a.expira_en > now()
      and a.texto_normalizado operator(extensions.%) p_texto_normalizado
      and extensions.similarity(a.texto_normalizado, p_texto_normalizado)
          >= greatest(p_umbral, 0.3)
    order by extensions.similarity(a.texto_normalizado, p_texto_normalizado) desc,
             a.verificado_en desc
    limit greatest(p_limite, 1);
end;
$$;

-- ── Guardar: una fila por afirmación; si ya existe, se actualiza y se renueva la vigencia ──
-- Vigencia (D5): 30 días, o 7 si el veredicto fue insuficiente (puede aparecer información nueva).
create function public.guardar_afirmacion_verificada(
    p_texto text,
    p_texto_normalizado text,
    p_hash_texto text,
    p_veredicto text,
    p_fuentes jsonb,
    p_modelo_llm text,
    p_version_prompts text,
    p_analisis_origen uuid
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_id uuid;
begin
    insert into public.afirmaciones_verificadas
        (texto, texto_normalizado, hash_texto, veredicto, fuentes, modelo_llm, version_prompts,
         verificado_en, expira_en, analisis_origen)
    values (
        p_texto, p_texto_normalizado, p_hash_texto, p_veredicto,
        coalesce(p_fuentes, '[]'::jsonb), p_modelo_llm, p_version_prompts,
        now(),
        now() + case when p_veredicto = 'insuficiente' then interval '7 days' else interval '30 days' end,
        p_analisis_origen
    )
    on conflict (hash_texto) do update
    set texto = excluded.texto,
        veredicto = excluded.veredicto,
        fuentes = excluded.fuentes,
        modelo_llm = excluded.modelo_llm,
        version_prompts = excluded.version_prompts,
        verificado_en = excluded.verificado_en,
        expira_en = excluded.expira_en,
        analisis_origen = excluded.analisis_origen
    returning id into v_id;
    return v_id;
end;
$$;

revoke execute on function public.buscar_afirmacion_verificada(text, text, real, integer)
    from public, anon, authenticated;
revoke execute on function public.guardar_afirmacion_verificada(
    text, text, text, text, jsonb, text, text, uuid
) from public, anon, authenticated;

grant execute on function public.buscar_afirmacion_verificada(text, text, real, integer)
    to service_role;
grant execute on function public.guardar_afirmacion_verificada(
    text, text, text, text, jsonb, text, text, uuid
) to service_role;

notify pgrst, 'reload schema';
