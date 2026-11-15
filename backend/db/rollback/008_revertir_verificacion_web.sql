-- Deshace backend/db/migrations/008_verificacion_web.sql.
-- ATENCIÓN: borra la base de afirmaciones verificadas y las columnas de la cola
-- (intentos, proximo_intento, ultimo_error, version_prompts, iniciado_en, terminado_en,
-- copiada_de). Las filas de verificaciones_web, y con ellas los resultados ya guardados
-- (estado, conclusión, resumen, afirmaciones, fuentes y modelo), se conservan; los datos
-- de los incrementos 1 y 3 no se tocan.
-- Antes de ejecutarlo, apagar el trabajador (VERIFICATION_ENABLED sin definir).

drop function if exists public.fallar_verificacion_web(uuid, text, integer, integer[]);
drop function if exists public.completar_verificacion_web(
    uuid, text, text, jsonb, jsonb, text, text
);
drop function if exists public.copiar_verificacion_web(uuid);
drop function if exists public.reclamar_verificacion_web(integer, integer);
drop function if exists public.encolar_verificaciones_pendientes(timestamptz, integer);
drop function if exists public.encolar_verificacion(uuid);

drop table if exists public.afirmaciones_verificadas;

drop index if exists public.verificaciones_web_cola_idx;

alter table public.verificaciones_web
    drop column if exists copiada_de,
    drop column if exists terminado_en,
    drop column if exists iniciado_en,
    drop column if exists version_prompts,
    drop column if exists ultimo_error,
    drop column if exists proximo_intento,
    drop column if exists intentos;

-- Si se aplicó con el MCP o la CLI de Supabase, quitar también su registro. Si se aplicó desde
-- el SQL Editor, ese registro no existe y no pasa nada.
do $$
begin
    delete from supabase_migrations.schema_migrations where name = 'verificacion_web';
exception
    when undefined_table or invalid_schema_name then
        null;
end;
$$;

notify pgrst, 'reload schema';
