# SMART MONEY RADAR (SMR)

Repositório oficial privado do SMART MONEY RADAR.

## Importação inicial da base recuperada

O repositório está sendo preparado para receber a base de código recuperada da Etapa 16. Para concluir a importação pelo GitHub, envie estes três arquivos ZIP para a raiz deste repositório usando **Add file → Upload files**:

1. `SMR-CODIGO-BASE-ETAPA16-2026-11-16.zip`
2. `SMR-ETAPA16-RECUPERACAO-ANDROID-2026-11-16.zip`
3. `SMR-VALIDACAO-UNIFICADA-ETAPA16.zip`

O workflow `.github/workflows/import-smr-archives.yml` extrairá e combinará os pacotes, removerá os arquivos ZIP e caches, executará os testes e a compilação e só então fará o commit dos arquivos do projeto.

**Não envie arquivos `.env`, credenciais, chaves privadas, bancos SQLite ou mapas confidenciais.** Os pacotes preparados foram verificados para não conter esses itens.

## Estado técnico conhecido da base recuperada

- Solana V1; monitoramento e coleta em modo somente leitura.
- Parser conservador, normalização, monitor WebSocket, persistência SQLite.
- Coletor RPC, auditoria e anonimização de fixtures.
- BUY/SELL/UNKNOWN e reconstrutor econômico ainda não devem ser considerados implementados apenas por constarem no planejamento.
- A aprovação semântica de fixtures reais exige revisão humana.

O Registro Mestre versionado no repositório será a fonte de verdade para as próximas etapas.
