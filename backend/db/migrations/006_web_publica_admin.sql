-- Web pública (feed en vivo) y panel de administración. Aplicar después de 005.
-- El backend lee el feed y los casos con la clave secreta (service_role) y nunca
-- devuelve usuario_id; el rol de administrador se comprueba en la API.

-- El administrador puede retirar un caso del feed público sin borrarlo.
alter table public.analisis
    add column oculto boolean not null default false;

-- Probabilidad unificada como número: permite filtrar por nivel y ordenar.
alter table public.analisis
    add column probabilidad_unificada double precision
        generated always as ((resultado_unificado->>'probabilidad_falsa')::double precision) stored;

-- Feed público y lista de casos: los más recientes primero.
create index analisis_fecha_idx on public.analisis (fecha desc, id desc);
create index analisis_publico_fecha_idx
    on public.analisis (fecha desc, id desc)
    where not oculto;

grant update (oculto) on public.analisis to service_role;

-- Rol de administrador en app_metadata (solo editable con la clave secreta).
-- Se deja disponible para futuras políticas RLS.
create function public.es_admin()
returns boolean
language sql
stable
set search_path = ''
as $$
    select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'admin';
$$;

revoke execute on function public.es_admin() from public, anon;
grant execute on function public.es_admin() to authenticated, service_role;

-- Uso de cada versión de modelo: casos, salida media para falsa y fechas.
-- Base de la comparación de versiones del panel de administración.
create function public.resumen_versiones_modelo()
returns table (
    modelo text,
    version text,
    casos bigint,
    probabilidad_media double precision,
    primer_uso timestamptz,
    ultimo_uso timestamptz
)
language sql
stable
set search_path = ''
as $$
    select r.modelo,
           r.version,
           count(*),
           avg(r.probabilidad_falsa),
           min(a.fecha),
           max(a.fecha)
    from public.resultados_modelo as r
    join public.analisis as a on a.id = r.analisis_id
    group by r.modelo, r.version
    order by r.modelo, max(a.fecha) desc;
$$;

revoke execute on function public.resumen_versiones_modelo() from public, anon, authenticated;
grant execute on function public.resumen_versiones_modelo() to service_role;

notify pgrst, 'reload schema';
