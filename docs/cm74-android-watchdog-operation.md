# CM74 — Operação do watchdog Android (somente leitura)

Este mecanismo supervisiona exclusivamente o dashboard HTTP local `127.0.0.1:8765`. Não habilita captura live, negociação, execução de ordens ou acesso externo.

## Pré-requisitos

- Termux com `bash`, `python` e `flock` (normalmente disponibilizado por `util-linux`).
- Banco SQLite **já existente e compatível** com o dashboard.
- Checkout local da branch contendo os scripts.

## Iniciar em primeiro plano

```bash
export SMR_DB_PATH="$HOME/smr-eval.HHwaLhr5/evaluation.sqlite"
bash tools/loop_smr_dashboard_watchdog_android.sh
```

O caminho é apenas um exemplo: confirme o local real do arquivo antes de executar. O loop verifica a cada 60 segundos, por padrão. Ajustes opcionais:

```bash
export SMR_DASHBOARD_WATCH_INTERVAL=60
export SMR_DASHBOARD_WATCH_MAX_FAILURES=3
```

O script mantém um bloqueio exclusivo em `~/.local/state/smr-dashboard/watchdog.lock` e termina após o número configurado de falhas consecutivas. Execute `Ctrl+C` para interromper o loop em primeiro plano. Não existe serviço de inicialização automática no boot nesta etapa.

## Limites de homologação

- A CI valida a lógica e a sintaxe em Linux; não comprova execução física no Android.
- A verificação de saúde exige token privado, resposta autenticada e payload exato `{"status":"ok","mode":"read_only"}`; uma resposta HTTP 200 isolada não é aceita.
- O watchdog não encerra nem substitui processos existentes com PID ativo e endpoint indisponível; o inicializador falha fechado.
- Android pode suspender ou encerrar o processo. O uso de wake lock pelo inicializador não garante execução contínua.
- Logs e estado devem permanecer privados. Não publique tokens ou conteúdos do log.

## Próximos critérios de aceite

1. Validar em Termux real: recuperação após término do dashboard, sem duplicação.
2. Validar fisicamente no Termux a verificação autenticada já implementada e sua recuperação após queda.
3. Definir supervisor persistente e recuperação após reboot, com confirmação do usuário antes de configurar o dispositivo.
