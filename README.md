# SMART MONEY RADAR (SMR)

Repositório oficial privado do SMART MONEY RADAR.

## Importação inicial da base recuperada

O repositório está preparado para receber a base recuperada da Etapa 16. Para concluir a importação pelo GitHub, envie **somente este arquivo ZIP** para a raiz do repositório usando **Add file → Upload files**:

- `SMR-CODIGO-BASE-ETAPA16-2026-11-16.zip` — arquivo de código-base recuperado, com testes e Registro Mestre.

O workflow `.github/workflows/import-smr-archives.yml` extrairá o pacote, removerá caches, arquivos temporários e bancos locais, executará os testes e a compilação e só então fará o commit do código.

Não envie arquivos `.env`, credenciais, chaves privadas, bancos SQLite ou mapas confidenciais.

## Validação local do pacote recuperado

Verificação realizada no pacote de código-base Etapa 16:

- **95 testes aprovados**, 0 falhas.
- `compileall` aprovado.
- Varredura de credenciais: nenhum segredo real identificado; o arquivo `.env.example` contém apenas o placeholder `replace_with_your_helius_api_key`.
- Os testes são locais/simulados; não comprovam conexão Helius/Solana em produção.

## Estado técnico conhecido

- Solana V1; monitoramento e coleta em modo somente leitura.
- Parser conservador, normalização, monitor WebSocket, persistência SQLite.
- Coletor RPC, auditoria e anonimização de fixtures.
- BUY/SELL/UNKNOWN e reconstrutor econômico não devem ser considerados implementados apenas por constarem no planejamento.
- A aprovação semântica de fixtures reais exige revisão humana.

O Registro Mestre versionado no repositório será a fonte de verdade para as próximas etapas.
