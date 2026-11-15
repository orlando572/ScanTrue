-- Deshace backend/db/migrations/009_afirmaciones_verificadas.sql.
-- Solo borra las dos funciones: la tabla afirmaciones_verificadas y sus datos son de la 008
-- y se conservan.

drop function if exists public.guardar_afirmacion_verificada(
    text, text, text, text, jsonb, text, text, uuid
);
drop function if exists public.buscar_afirmacion_verificada(text, text, real, integer);

-- Si se aplicó con el MCP o la CLI de Supabase, quitar también su registro. Si se aplicó desde
-- el SQL Editor, ese registro no existe y no pasa nada.
do $$
begin
    delete from supabase_migrations.schema_migrations where name = 'afirmaciones_verificadas';
exception
    when undefined_table or invalid_schema_name then
        null;
end;
$$;

notify pgrst, 'reload schema';
