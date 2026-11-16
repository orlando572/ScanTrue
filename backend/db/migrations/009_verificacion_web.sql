-- Cola de verificación web (incremento 2, Fase 2) y base de afirmaciones ya verificadas.
-- Aplicar después de 008. Solo el backend, con la clave secreta (service_role), usa estas
-- funciones y tablas; el navegador no puede leerlas directamente.
--
-- Estados de verificaciones_web:
--   pendiente   en cola; también adonde vuelve un caso tras una falla pasajera.
--   en_proceso  reservado por un trabajador hasta proximo_intento; si la reserva vence, otro
--               trabajador lo retoma.
--   completada  final.
--   fallida     final: se llega a ella al agotar los intentos.

-- ── Columnas de la cola ──
-- copiada_de NO lleva clave foránea a propósito: una segunda relación entre analisis y
-- verificaciones_web haría ambigua la incrustación de PostgREST (error PGRST201, «Multiple
-- Choices») y rompería la web pública y el panel. Es solo informativa.
alter table public.verificaciones_web
    add column intentos integer not null default 0 check (intentos >= 0),
    add column proximo_intento timestamptz not null default now(),
    add column ultimo_error text,
    add column version_prompts text,
    add column iniciado_en timestamptz,
    add column terminado_en timestamptz,
    add column copiada_de uuid;

create index verificaciones_web_cola_idx
    on public.verificaciones_web (proximo_intento, analisis_id)
    where estado in ('pendiente', 'en_proceso');

-- ── Base de afirmaciones ya verificadas (la consulta llega en la Fase 3) ──
create table public.afirmaciones_verificadas (
    id uuid primary key default gen_random_uuid(),
    texto text not null check (char_length(texto) between 1 and 1000),
    texto_normalizado text not null,
    hash_texto text not null unique,
    veredicto text not null
        check (veredicto in ('apoyada', 'contradicha', 'fuera_de_contexto', 'insuficiente')),
    fuentes jsonb not null default '[]'::jsonb check (jsonb_typeof(fuentes) = 'array'),
    modelo_llm text,
    version_prompts text,
    verificado_en timestamptz not null default now(),
    expira_en timestamptz not null,
    -- Si el propietario borra su análisis, la base conserva la afirmación.
    analisis_origen uuid references public.analisis(id) on delete set null
);

create index afirmaciones_verificadas_trgm_idx
    on public.afirmaciones_verificadas using gin (texto_normalizado extensions.gin_trgm_ops);

alter table public.afirmaciones_verificadas enable row level security;
revoke all on public.afirmaciones_verificadas from anon, authenticated;
grant select, insert, update, delete on public.afirmaciones_verificadas to service_role;

-- ── Encolar: idempotente; devuelve true si creó la fila ──
create function public.encolar_verificacion(p_analisis_id uuid)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_filas integer;
begin
    insert into public.verificaciones_web (analisis_id)
    values (p_analisis_id)
    on conflict (analisis_id) do nothing;
    get diagnostics v_filas = row_count;
    return v_filas > 0;
end;
$$;

-- ── Barrido: encola los análisis sin fila posteriores a p_desde (D9) ──
-- Cubre el caso en que encolar falló al crear el análisis. Devuelve cuántos encoló.
create function public.encolar_verificaciones_pendientes(
    p_desde timestamptz,
    p_limite integer default 100
)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_filas integer;
begin
    insert into public.verificaciones_web (analisis_id)
    select a.id
    from public.analisis as a
    where a.fecha >= p_desde
      and not exists (
          select 1 from public.verificaciones_web as v where v.analisis_id = a.id
      )
    order by a.fecha, a.id
    limit greatest(p_limite, 0)
    on conflict (analisis_id) do nothing;
    get diagnostics v_filas = row_count;
    return v_filas;
end;
$$;

-- ── Reclamar: un caso a la vez, sin duplicar trabajo entre procesos (D6 y D11) ──
-- Orden: primero las discrepancias entre BiLSTM y BETO, luego los niveles 4 y 5
-- (probabilidad ≥ 0,605, el mismo corte de resumen_plataforma) y después los más antiguos.
-- La reserva (p_reserva_segundos) vence si el proceso se cae: otro lo retoma.
create function public.reclamar_verificacion_web(
    p_max_intentos integer default 3,
    p_reserva_segundos integer default 600
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_id uuid;
begin
    -- Un caso que ya agotó sus intentos (por ejemplo, porque el proceso se cayó cada vez)
    -- no se reclama más: queda fallida.
    update public.verificaciones_web
    set estado = 'fallida',
        ultimo_error = coalesce(ultimo_error, 'intentos_agotados'),
        terminado_en = now(),
        actualizado_en = now()
    where estado in ('pendiente', 'en_proceso')
      and proximo_intento <= now()
      and intentos >= p_max_intentos;

    select v.analisis_id into v_id
    from public.verificaciones_web as v
    join public.analisis as a on a.id = v.analisis_id
    where v.estado in ('pendiente', 'en_proceso')
      and v.proximo_intento <= now()
    order by coalesce(a.discrepa, false) desc,
             coalesce(a.probabilidad_unificada >= 0.605, false) desc,
             a.fecha asc,
             v.analisis_id
    for update of v skip locked
    limit 1;

    if v_id is null then
        return null;
    end if;

    update public.verificaciones_web
    set estado = 'en_proceso',
        intentos = intentos + 1,
        iniciado_en = now(),
        terminado_en = null,
        proximo_intento = now() + make_interval(secs => p_reserva_segundos),
        ultimo_error = null,
        actualizado_en = now()
    where analisis_id = v_id;
    return v_id;
end;
$$;

-- ── Copiar: si el mismo texto ya tiene una verificación vigente, se reutiliza (D5, D10) ──
-- Vigencia: 30 días desde que se terminó la original, o 7 si concluyó evidencia_insuficiente.
-- La copia conserva la fecha de la original, así copiar no alarga la vida del resultado.
create function public.copiar_verificacion_web(p_analisis_id uuid)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_origen public.verificaciones_web%rowtype;
begin
    select o.* into v_origen
    from public.analisis as actual
    join public.analisis as otro
        on otro.hash_texto = actual.hash_texto and otro.id <> actual.id
    join public.verificaciones_web as o on o.analisis_id = otro.id
    where actual.id = p_analisis_id
      and o.estado = 'completada'
      and o.terminado_en is not null
      and o.terminado_en >= now() - case
              when o.conclusion = 'evidencia_insuficiente' then interval '7 days'
              else interval '30 days'
          end
    order by o.terminado_en desc
    limit 1;

    if not found then
        return false;
    end if;

    update public.verificaciones_web
    set estado = 'completada',
        conclusion = v_origen.conclusion,
        resumen = v_origen.resumen,
        afirmaciones = v_origen.afirmaciones,
        fuentes = v_origen.fuentes,
        modelo_llm = v_origen.modelo_llm,
        version_prompts = v_origen.version_prompts,
        copiada_de = v_origen.analisis_id,
        terminado_en = v_origen.terminado_en,
        ultimo_error = null,
        actualizado_en = now()
    where analisis_id = p_analisis_id
      and estado = 'en_proceso';
    return found;
end;
$$;

-- ── Completar: guarda el resultado en una sola operación ──
-- Devuelve false si el caso ya no estaba en_proceso (por ejemplo, se borró el análisis).
create function public.completar_verificacion_web(
    p_analisis_id uuid,
    p_conclusion text,
    p_resumen text,
    p_afirmaciones jsonb,
    p_fuentes jsonb,
    p_modelo_llm text,
    p_version_prompts text
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
begin
    update public.verificaciones_web
    set estado = 'completada',
        conclusion = p_conclusion,
        resumen = p_resumen,
        afirmaciones = coalesce(p_afirmaciones, '[]'::jsonb),
        fuentes = coalesce(p_fuentes, '[]'::jsonb),
        modelo_llm = p_modelo_llm,
        version_prompts = p_version_prompts,
        terminado_en = now(),
        ultimo_error = null,
        actualizado_en = now()
    where analisis_id = p_analisis_id
      and estado = 'en_proceso';
    return found;
end;
$$;

-- ── Fallar: vuelve a la cola con espera creciente o queda fallida (D11) ──
-- p_esperas son los segundos de espera tras el 1.º, 2.º, 3.º… intento; si hay más intentos
-- que valores, se repite el último. Devuelve el estado nuevo, o null si el caso ya no
-- estaba en_proceso.
create function public.fallar_verificacion_web(
    p_analisis_id uuid,
    p_error text,
    p_max_intentos integer default 3,
    p_esperas integer[] default array[60, 300, 900]
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_estado text;
begin
    update public.verificaciones_web
    set estado = case when intentos >= p_max_intentos then 'fallida' else 'pendiente' end,
        ultimo_error = left(p_error, 200),
        proximo_intento = now() + make_interval(
            secs => p_esperas[least(greatest(intentos, 1), cardinality(p_esperas))]
        ),
        terminado_en = case when intentos >= p_max_intentos then now() end,
        actualizado_en = now()
    where analisis_id = p_analisis_id
      and estado = 'en_proceso'
    returning estado into v_estado;
    return v_estado;
end;
$$;

revoke execute on function public.encolar_verificacion(uuid)
    from public, anon, authenticated;
revoke execute on function public.encolar_verificaciones_pendientes(timestamptz, integer)
    from public, anon, authenticated;
revoke execute on function public.reclamar_verificacion_web(integer, integer)
    from public, anon, authenticated;
revoke execute on function public.copiar_verificacion_web(uuid)
    from public, anon, authenticated;
revoke execute on function public.completar_verificacion_web(
    uuid, text, text, jsonb, jsonb, text, text
) from public, anon, authenticated;
revoke execute on function public.fallar_verificacion_web(uuid, text, integer, integer[])
    from public, anon, authenticated;

grant execute on function public.encolar_verificacion(uuid) to service_role;
grant execute on function public.encolar_verificaciones_pendientes(timestamptz, integer)
    to service_role;
grant execute on function public.reclamar_verificacion_web(integer, integer) to service_role;
grant execute on function public.copiar_verificacion_web(uuid) to service_role;
grant execute on function public.completar_verificacion_web(
    uuid, text, text, jsonb, jsonb, text, text
) to service_role;
grant execute on function public.fallar_verificacion_web(uuid, text, integer, integer[])
    to service_role;

notify pgrst, 'reload schema';
