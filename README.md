# Minuto com Jesus

Site público do projeto Minuto com Jesus.

Este repositório contém apenas os arquivos necessários para publicar a página. O desenvolvimento e o envio de e-mails são mantidos separadamente.

Antes do upload, `tools/site/check.py` confere preço mensal, disponibilidade, documentos e anexo por hash, amostra de Tiago 4:8, assets, links locais e recursos inesperados. O backend canônico é lido no CI e novamente antes do empacotamento. Os 16 testes exercitam recusas concretas; nenhum envio ou operação financeira faz parte da validação.

`site/release.json` descreve o pacote revisado. O estado atual é `coming_soon`, com abertura não autorizada. A admissão restrita a uma pessoa pode coexistir com esta página. Publicar um CTA aberto exige autorização no pacote e saúde com inscrições ativas no limite público declarado; o PR #6 permanece em rascunho até a liberação correspondente. A conferência é pontual e não garante disponibilidade futura nem substitui o aceite financeiro, editorial e contratual.

A cópia deste diretório e os validadores são mantidos no repositório privado. Sua CI compara os blobs do espelho com este repositório antes de aceitar divergências. Não atualizar apenas uma das cópias.

Execução local: `python -m unittest discover -s tools/site -p 'test_*.py' -v` e `python tools/site/check.py`. A opção `--check-backend` exige acesso HTTPS ao backend.
