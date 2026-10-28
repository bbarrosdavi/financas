# Celular: MacroDroid mandando o push do banco

O celular lê a notificação do Nubank (e do PicPay, se quiser) e manda para o site.
O site não deve ficar aberto na internet: o caminho simples é uma VPN como o
Tailscale, com a porta publicada só no IP da VPN (`PORTA` no `.env`). Assim só os
seus aparelhos chegam ao site, e o túnel já cifra o tráfego.

## 0. Antes

- A VPN instalada e conectada no celular.
- Algumas redes (de universidade, de empresa) bloqueiam a VPN. Nelas o push só chega
  pelo 4G; o que não chegar é coberto quando você importar o extrato.

## 1. Não deixar o Android matar o MacroDroid

1. Configurações → Apps → MacroDroid → Bateria → **Sem restrições**.
2. No MacroDroid: Configurações → **Serviço em primeiro plano** ligado.
3. Dê ao MacroDroid o acesso a notificações quando ele pedir.

## 2. Gatilho

Adicionar macro `Finanças`:
- Gatilho: **Notificação recebida**.
- Aplicativos: **Nubank** (`com.nu.production`); opcional: PicPay, Mercado Pago.
- Conteúdo: qualquer.

## 3. Ação

Ação: **Aplicativos → Requisição HTTP**. Abra o site no celular, vá em
**Ajustes → Celular** e copie cada campo:

| Campo da ação | Valor |
|---|---|
| Método | `POST` |
| URL | o campo "URL" de Ajustes |
| Header Params | `Authorization` = o campo "Cabeçalho Authorization" |
| Content Body | tipo `application/json`, conteúdo = o campo "Corpo" |

Não adicione `Content-Type` à mão: escolher o tipo já manda o cabeçalho.

O corpo usa o *magic text* do gatilho com **chaves** (`{not_title}`, `{notification}`,
`{not_app_package}`). Com colchetes o MacroDroid manda o texto literal e nada é lido.

## 4. Repetir se falhar (recomendado)

Sem rede, o envio falha e o push se perde. Para tentar de novo:
1. Na ação HTTP, ligue **Salvar código de retorno** numa variável inteira `cod`.
2. Depois dela: **Se `cod` diferente de 202** → **Aguardar 60 s** → repetir a ação HTTP
   (até 5 vezes). Repetir é seguro: o servidor descarta o mesmo push dentro de 10 minutos.

## 5. Conferir

Não use "Testar ações" do menu da macro: sem notificação real, o magic text vai literal.
Faça uma compra pequena. Em segundos o lançamento aparece em **Lançamentos**; se o lugar
não for conhecido, vai para **Pendentes** e chega um aviso, se você configurou a entrega
(ver `deploy/`).

Códigos: `202` aceito (inclusive repetido), `401` chave errada ou ausente, `422` JSON quebrado.
