# Finanças

Site para controlar o dinheiro pessoal no lugar da planilha. Importa extrato e fatura do banco, recebe pelo
celular o push que o banco manda a cada compra e divide cada lançamento em partes: gasto, renda,
transferência entre contas suas, acerto com pessoas e poupança em metas. Roda num servidor seu, com Docker, e
abre no PC ou no celular (dá para instalar como app pelo navegador).

![Painel](docs/prints/painel.png)

Os prints usam um banco de demonstração com pessoas, lugares e valores inventados.

## Telas

| | |
|---|---|
| ![Pendentes](docs/prints/pendentes.png) | ![Lançamentos](docs/prints/lancamentos.png) |
| **Pendentes**: o que o sistema não classifica sozinho, com a sugestão e as categorias a um toque. | **Lançamentos**: filtros, a primeira linha para lançar à mão e o saldo da conta linha a linha. |
| ![Orçamento](docs/prints/orcamento.png) | ![Pessoas](docs/prints/pessoas.png) |
| **Orçamento**: categoria por mês (orçado, realizado e diferença) e despesas fixas por item. | **Pessoas**: quem te deve e a quem você deve, contas que alguém pagou por você e os acertos. |
| ![Projeção](docs/prints/projecao.png) | ![Importar](docs/prints/importar.png) |
| **Projeção**: mês a mês até o horizonte, com eventos como uma viagem ou uma renda que acaba. | **Importar**: extrato e fatura em PDF, CSV ou Excel; o que já existe não duplica. |

O **Painel** resume semana, mês ou ano: resultado, quanto ainda dá para gastar nas categorias variáveis,
cada categoria contra o teto (e contra o período anterior), entradas e gastos dos últimos 12 meses e para
onde foi o dinheiro. Os cartões se arrastam e se redimensionam. Em **Ajustes** ficam o tema claro ou escuro,
o estilo dos painéis (Vidro, Sólido, Contorno ou Plano), o papel de parede, as pessoas e os dados para o
celular.

![Painel no tema escuro](docs/prints/painel-escuro.png)

## Como o dinheiro é representado

Um **lançamento** é um movimento numa conta (Nubank conta, Nubank cartão, PicPay, Bradesco), com o sinal da
conta. O significado está nas **partes**, que somam o valor do lançamento, cada uma com uma natureza:

| natureza | o que é | exemplo |
|---|---|---|
| gasto | consumo seu, com categoria | mercado, Uber, sua parte do aluguel |
| renda | dinheiro que é seu | salário, ajuda dos pais |
| transferencia | entre contas suas | pagar a fatura, Pix no crédito caindo na conta |
| acerto | alguém te deve ou você deve | a parte de um colega no boleto do aluguel |
| poupanca | dinheiro seu indo para uma meta | aporte na reserva de emergência |

O boleto do aluguel dividido com dois colegas vira a sua parte como gasto mais dois acertos; o Pix de um
deles devolvendo a parte dele é acerto; a conta que um colega pagou por você é um lançamento de valor 0 com
gasto e acerto. Nada de despesa negativa inventada. Lançamento com parte sem categoria (ou acerto sem
pessoa) é **pendente** e o site pergunta.

## Entradas

1. **Celular**: o MacroDroid manda o push do banco para `/api/v1/transaction/webhook` (ver
   [docs/MACRODROID.md](docs/MACRODROID.md)).
2. **Arquivos**, na tela Importar (o tipo é reconhecido pelo conteúdo, não pelo nome):
   - Nubank: extrato e fatura em PDF ou CSV (`app/importadores.py`).
   - Bradesco (`app/bradesco.py`): extrato em PDF, CSV ou Excel (.xlsx), conferido pelo total e pela corrente
     de saldos; e a fatura em aberto que o aplicativo gera em PDF, que é só imagem e é lida por OCR
     (tesseract com português, relendo data e valor de cada linha só com dígitos). Cada cartão tem que fechar
     com o "Total para" impresso, senão nada entra. Na primeira importação nascem as contas Bradesco (com o
     saldo anterior ao primeiro lançamento do extrato) e Cartão Bradesco (devendo o saldo anterior da fatura).

   Extrato que não fecha é recusado; o que já existe (mesmo arquivo, outro formato do mesmo extrato, ou o que
   veio pelo celular) não duplica.
3. **À mão**: o que não passa pelo banco.

## Classificação

- **Automático** só o que é verdade por definição: pagamento de fatura saindo da conta, pagamento no cartão
  com o par saindo da conta, Pix no crédito, dinheiro vindo de conta sua (com `TITULAR` no `.env`), a taxa da
  recarga do PicPay no crédito, a parcela seguinte de um parcelamento já classificado e estabelecimento
  conhecido (regras do sistema em `app/categorias.py`).
- **Sugestão**, que fica pendente até você confirmar: Pix de ou para uma pessoa (o mesmo Pix pode ter outra
  finalidade), o boleto da imobiliária dividido pelo rateio de Ajustes, e o que você marcou para sugerir da
  próxima vez no mesmo lugar.

Pendente novo pode gerar um aviso (ver [Avisos](#avisos)).

## Instalação

Com Docker:

```sh
git clone https://github.com/bbarrosdavi/financas.git
cd financas
cp .env.example .env        # API_KEY e SESSION_SECRET: openssl rand -hex 32; WEB_PASSWORD: a senha do site
mkdir -p ~/.local/share/financas ~/.local/state/financas/avisos
UID_HOST=$(id -u) docker compose up -d --build
```

O site abre em `http://localhost:8095`. O banco (SQLite) e os papéis de parede ficam em
`~/.local/share/financas`. Para o celular chegar ao site, publique a porta no IP de uma VPN ou da rede de
casa (`PORTA` no `.env`) e ponha em `URL_PUBLICA` o endereço que o celular usa. Não exponha o site direto na
internet.

Fora do Docker, com Python 3.12 ou mais novo: ler PDF precisa do `pdftotext`/`pdftoppm` (poppler) e a fatura
do Bradesco precisa do `tesseract` com português (`tesseract-ocr-por`). No `.env`, aponte `DATABASE_PATH` e
`PAPEIS_DIR` para pastas suas e rode:

```sh
pip install -r requirements.txt
uvicorn app.main:app --port 8095
```

Testes:

```sh
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

## Avisos

O container não manda mensagem: ele deixa cada aviso de pendente num arquivo da fila
(`~/.local/state/financas/avisos`), no máximo um a cada 10 minutos. Quem entrega é o host: copie as units de
`deploy/` para `~/.config/systemd/user/` e rode `systemctl --user enable --now financas-avisos.path`. O
comando de entrega vai em `AVISAR`, na unit `financas-avisos.service`, e recebe o remetente e o texto; sem
ele, o aviso vai para o journal.

## Exportar

Em Ajustes: **Baixar tabelas (.xlsx)**, uma aba por tabela. **Baixar no modelo antigo (.ods)** preenche a
planilha Budget Dashboard da The Office Lab pelo LibreOffice. Esse modelo é comercial e não vem no
repositório: coloque o seu em `app/modelo/planilha.ods` (antes do `docker compose build`) e rode
`python scripts/limpar_modelo_ods.py app/modelo/planilha.ods` nele uma vez.
