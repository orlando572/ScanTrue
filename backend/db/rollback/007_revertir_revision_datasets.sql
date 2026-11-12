-- Deshace backend/db/migrations/007_revision_datasets.sql.
-- ATENCIÓN: borra las revisiones del administrador y las versiones de dataset.
-- Los análisis y sus resultados se conservan; se pierden los fragmentos separados,
-- el texto original y el texto por modelo guardados desde la 007.
-- Antes de ejecutarlo, volver a una versión del backend que use
-- crear_analisis_texto_unico (o dejar que el backend actual recurra a ella).

drop function if exists public.resumen_plataforma(boolean);
drop function if exists public.crear_version_dataset(text, text, uuid, jsonb, jsonb);
drop function if exists public.crear_analisis_con_fragmentos(
    uuid, text, text, text, text, jsonb, jsonb, text, jsonb, boolean
);

drop table if exists public.dataset_items;
drop table if exists public.datasets_version;
drop table if exists public.revisiones;
drop table if exists public.verificaciones_web;

drop index if exists public.analisis_texto_trgm_idx;
drop index if exists public.analisis_prioridad_idx;
drop index if exists public.analisis_dominio_idx;
drop index if exists public.analisis_probabilidad_idx;

alter table public.resultados_modelo drop column if exists texto_modelo;

alter table public.analisis
    drop column if exists discrepa,
    drop column if exists dominio,
    drop column if exists texto_recortado,
    drop column if exists fragmentos,
    drop column if exists texto_original;

-- Si se aplicó con el MCP o la CLI de Supabase, quitar también su registro:
delete from supabase_migrations.schema_migrations where name = 'revision_datasets';

notify pgrst, 'reload schema';
