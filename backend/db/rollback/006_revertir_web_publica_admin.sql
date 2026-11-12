-- Deshace backend/db/migrations/006_web_publica_admin.sql.
-- Solo quita lo que añadió la 006: no toca análisis, resultados ni cuentas.
-- Se pierde únicamente qué casos estaban ocultos del feed público.
-- Después de ejecutarlo, la web pública y el panel dejan de funcionar
-- (la extensión sigue igual).

drop function if exists public.resumen_versiones_modelo();
drop function if exists public.es_admin();

drop index if exists public.analisis_publico_fecha_idx;
drop index if exists public.analisis_fecha_idx;

revoke update (oculto) on public.analisis from service_role;

alter table public.analisis drop column if exists probabilidad_unificada;
alter table public.analisis drop column if exists oculto;

-- Opcional: quitar el rol de administrador.
-- update auth.users set raw_app_meta_data = raw_app_meta_data - 'role'
-- where raw_app_meta_data->>'role' = 'admin';

-- Si se aplicó con el MCP o la CLI de Supabase, quitar también su registro:
delete from supabase_migrations.schema_migrations where name = 'web_publica_admin';

notify pgrst, 'reload schema';
