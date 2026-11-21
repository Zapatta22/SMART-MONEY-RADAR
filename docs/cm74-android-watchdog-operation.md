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

## Verificação local do ensaio offline isolado

O ensaio de supervisor de ambos os radares **não** utiliza o banco de produção e não captura a rede Solana. Para iniciar um ensaio curto de diagnóstico no Termux (sem habilitar ordens):

```bash
bash tools/run_smr_android_soak.sh --duration-seconds 120 --interval-seconds 5
```

O comando imprime o diretório privado `~/smr-soak-results/smr-soak-*` utilizado. Depois de encerrado, execute com o caminho exato impresso (substitua `DIRETORIO`):

```bash
PYTHONPATH=src python tools/verify_smr_android_soak.py DIRETORIO
```

O verificador confronta o relatório final com o journal de progresso e os checkpoints persistidos dos dois radares, executa `PRAGMA integrity_check` em SQLite aberto em modo somente leitura e rejeita ausência ou inconsistência dos artefatos. `accepted_offline=true` confirma somente a consistência do ensaio local limitado; os campos `physical_android_verified` e `autonomy_24h_verified` permanecem `false` até uma homologação física independente. Um ensaio de 120 segundos não demonstra autonomia de 24 horas. O verificador não acessa a rede, não modifica o banco e não executa operações financeiras.
