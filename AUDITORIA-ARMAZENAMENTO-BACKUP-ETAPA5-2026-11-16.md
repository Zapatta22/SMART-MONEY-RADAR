# SMR — Auditoria de armazenamento, integridade e backup (Etapa 5)

Data: 16/11/2026
Escopo: cópia local de auditoria do `smart-money-radar`; não representa deploy no ambiente do usuário.

## Alterações implementadas

1. Conexões SQLite em disco passam a usar `timeout=15s`, `PRAGMA busy_timeout=15000`, `journal_mode=WAL` e `synchronous=NORMAL`.
2. `SQLiteEventStore.integrity_check()` executa `PRAGMA integrity_check` e retorna as linhas do resultado.
3. `SQLiteEventStore.storage_stats()` retorna contagens de `activity_events`, `observed_transactions`, `processed_signatures` e `wallet_checkpoints`, além de page_count, page_size e tamanho lógico estimado.
4. `SQLiteEventStore.backup_to(destination)` usa a API online-backup do SQLite, cria os diretórios de destino, impede sobrescrever o próprio banco de origem e valida o banco de backup com `PRAGMA integrity_check` antes de concluir.
5. Novos testes verificam integridade, estatísticas, restauração de payload/checkpoint e rejeição de destino igual à origem.

## Resultado de validação

- `PYTHONPATH=src python -m unittest discover -s tests -v`: 44 testes aprovados, 0 falhas.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- O teste de restauração abriu o backup como um novo `SQLiteEventStore`, validou `integrity_check = ok`, recuperou o checkpoint e comparou o payload bruto.
- Testes locais/simulados; sem RPC real, benchmark, teste de carga, falha de disco ou VPS.

## Limitações e riscos ainda abertos

- Não há agendador automático para executar backups, rotação, retenção ou alerta de falha.
- Não há cópia off-site nem criptografia do artefato de backup; o diretório de destino precisa ter permissões e proteção adequadas no host.
- `storage_stats()` estima tamanho lógico pelo número de páginas; não contabiliza necessariamente WAL/SHM e espaço recuperável.
- `WAL` melhora concorrência local, mas não substitui política de backup, teste de restauração periódico ou monitoramento do disco.
- A política de retenção de payload bruto não foi definida. Não apagar dados automaticamente antes de definir prazo, volume e requisitos de replay.
- A cópia segue somente leitura em relação à blockchain: não assina nem envia transações.

## Próxima etapa recomendada

Auditar o ciclo operacional de dados: agendamento externo de backup, verificação de backup recente, alerta de espaço, restauração documentada e política de retenção configurável (inicialmente sem exclusão automática). Depois concluir o inventário de módulos e dependências para integração da V1.
