-- Cola durable del registro local. Solo el backend actualiza su estado.
alter table public.analisis
    add column intentos_blockchain integer not null default 0
        check (intentos_blockchain >= 0),
    add column proximo_intento_blockchain timestamptz not null default now(),
    add column ultimo_error_blockchain text;

alter table public.analisis
    alter column estado_blockchain set default 'pendiente';

update public.analisis
set estado_blockchain = 'pendiente'
where estado_blockchain = 'no_iniciado';

create index analisis_blockchain_cola_idx
    on public.analisis (proximo_intento_blockchain, id)
    where estado_blockchain in ('pendiente', 'fallido');

grant select on public.analisis, public.resultados_modelo to service_role;
grant update (estado_blockchain, hash_transaccion, intentos_blockchain,
              proximo_intento_blockchain, ultimo_error_blockchain)
    on public.analisis to service_role;

-- El bloqueo y el vencimiento de la reserva evitan trabajo duplicado entre procesos.
create function public.reclamar_registro_blockchain()
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_id uuid;
begin
    select a.id into v_id
    from public.analisis a
    where a.estado_blockchain in ('pendiente', 'fallido')
      and a.proximo_intento_blockchain <= now()
    order by a.proximo_intento_blockchain, a.id
    for update skip locked
    limit 1;

    if v_id is null then
        return null;
    end if;

    update public.analisis
    set estado_blockchain = 'pendiente',
        intentos_blockchain = intentos_blockchain + 1,
        proximo_intento_blockchain = now() + interval '60 seconds',
        ultimo_error_blockchain = null
    where id = v_id;
    return v_id;
end;
$$;

revoke execute on function public.reclamar_registro_blockchain()
    from public, anon, authenticated;
grant execute on function public.reclamar_registro_blockchain()
    to service_role;
