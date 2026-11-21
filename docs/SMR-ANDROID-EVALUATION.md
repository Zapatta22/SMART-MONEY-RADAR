# Avaliação Android/Termux — CM37
## Escopo
A avaliação utiliza o commit aprovado 764e04a8d86de88511911de4e968672876c25ef2, com 1.189 testes aprovados na CI 44858480081. O painel é somente leitura, local (127.0.0.1). Não executa ordens nem comandos administrativos HTTP. Nenhuma chave privada ou credencial de mercado é necessária.
## Preparação e inicialização
Em Termux, instale os requisitos básicos se ainda não estiverem disponíveis: `pkg install git python curl`. Depois, a partir de uma cópia atualizada desta branch, execute `bash tools/install_smr_android_eval.sh`. O script cria um diretório privado novo, obtém o commit fixado, confirma o SHA, instala dependências em venv, cria um banco vazio exclusivo de avaliação, valida o schema/integridade e chama o inicializador existente. A ausência de dados será exibida como indisponibilidade, sem resultados fabricados.
Para avaliar dados locais existentes, defina SMR_EVAL_SOURCE_DB com o caminho do arquivo próprio e execute o mesmo script. A origem é aberta apenas para leitura e copiada com SQLite backup para o novo diretório; não há migração da origem. O arquivo copiado contém os dados existentes e deve permanecer privado. Não use um banco não confiável.
## Acesso e PWA
Abra http://127.0.0.1:8765/ no navegador do mesmo Android. Copie o token temporário mostrado no Termux no campo de acesso. Não compartilhe o token. No Chrome, use o menu > Adicionar à tela inicial/Instalar aplicativo, quando oferecido. Não configure encaminhamento de porta, proxy público ou IP externo. O Service Worker não armazena credenciais/dados financeiros. Sem o processo local, não há garantia de acesso offline ao painel.
## Encerramento e diagnóstico
Ctrl+C no Termux encerra o servidor. Feche a aba do painel para descartar a sessão em memória. Se a porta estiver ocupada, encerre o processo anterior; não exponha outra interface. Em caso de erro, registre a versão do Android/Termux/Python, SHA e mensagem sanitizada, sem token, senha ou conteúdo financeiro. Preserve o banco original e os diretórios de avaliação até revisão.
## Matriz de validação física
| Verificação | Critério | Estado |
|---|---|---|
| Fetch e SHA fixado | código correto, checkout isolado | PENDENTE ANDROID |
| Dependências | Python e SQLite funcionais | PENDENTE ANDROID |
| Banco | origem intacta, cópia íntegra | PENDENTE ANDROID |
| Loopback | acesso somente no aparelho | PENDENTE ANDROID |
| PWA | ícone, instalação, modo standalone | PENDENTE ANDROID |
| Responsividade | navegação e gráficos em tela pequena | PENDENTE ANDROID |
| Offline | não mostrar dados como atualizados; sem cache sensível | PENDENTE ANDROID |
| Encerramento | sem processo residual | PENDENTE ANDROID |
CI desktop não substitui execução física. Não há homologação live ou autonomia 24h.

O instalador fixa explicitamente 127.0.0.1:8765, não aceita argumentos de rede, verifica a versão Python >=3.11 e testa importações das dependências. CI específica Python 3.14 adicionada; compatibilidade Android física e disponibilidade de wheels no Termux ainda requerem avaliação real.
