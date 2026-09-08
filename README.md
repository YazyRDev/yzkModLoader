# yzkModLoader

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

App desktop para buscar e baixar **mods** (Fabric, Forge, NeoForge, Quilt),
**resource packs**, **plugins** e **modpacks** direto do
[Modrinth](https://modrinth.com), com GUI dark inspirada no próprio site do
Modrinth.

Pode salvar os arquivos direto nas suas pastas locais (`mods`, `resourcepacks`) ou,
no caso de plugins, enviar direto para um servidor Purpur hospedado via SFTP.

Também cria e compartilha **modpacks próprios** (`.yzk`) e **pacotes de resource
packs próprios** (`.yzkrp`) em formatos de arquivo customizados — quando alguém
recebe um desses arquivos e clica duas vezes nele (no Windows), ele abre direto
no yzkModLoader e instala automaticamente.

> Projeto pessoal, feito para uso próprio e aberto para quem quiser usar,
> estudar ou contribuir. Veja [CONTRIBUTING.md](CONTRIBUTING.md) se quiser
> ajudar.

## 1. Instalar

Precisa do Python 3.9+ instalado.

```bash
git clone https://github.com/YzkModLoad/yzkModLoader.git
cd yzkModLoader
pip install -r requirements.txt
```

## 2. Rodar

```bash
python yzkModLoader.pyw
```

Na primeira execução o app vai avisar para você configurar as pastas, e vai pedir
permissão de administrador (UAC) para associar os arquivos `.yzk`/`.yzkrp` no
Windows — veja a seção 7 para detalhes.

## 3. Configurações (ícone ⚙ na barra lateral)

- **Chave da API do Modrinth (opcional):** não é necessária para buscar e baixar.
  Só use se quiser vincular ações à sua conta Modrinth (gerada em
  modrinth.com → Configurações → PAT).
- **Pasta de mods:** onde os `.jar` de mods (Fabric) vão ser salvos.
- **Pasta de resource packs:** onde os resource packs baixados vão ser salvos.
- **Servidor Purpur (opcional, só pra Plugins):**
  - Host/IP, porta SFTP (geralmente 22), usuário e senha (ou caminho de uma
    chave privada, se preferir autenticação por chave em vez de senha).
  - Pasta de plugins no servidor (geralmente `/plugins`).

O app **sempre pede pra você escolher a pasta** antes de baixar qualquer coisa —
nada é salvo em lugar nenhum sem você ter definido o destino primeiro.

## 4. Usando: Mods, Resource Packs e Plugins

1. Escolha a aba: **Mods**, **Resource Packs** ou **Plugins**.
   - Ao abrir a aba pela primeira vez (na sessão atual), o app já carrega
     automaticamente os itens **mais populares** (mais baixados) daquele
     tipo, pra sempre ter algo relevante na tela sem precisar buscar nada.
2. **Versão do Minecraft:** é um campo de seleção com autocompletar, preenchido
   com as versões reais do Minecraft (buscadas do Modrinth). Você pode digitar
   pra filtrar a lista (ex: digitar "1.21" mostra só as `1.21.x`) ou deixar em
   "Qualquer". Isso evita erro de digitação — você só escolhe entre versões
   que realmente existem.
3. **Loader (só na aba Mods):** escolha entre Fabric, Forge, NeoForge, Quilt
   ou Qualquer. A busca e o download já filtram pelo loader escolhido.
4. Digite o nome do que você procura e aperte **Buscar** (ou Enter).
5. **Seleção múltipla (bulk download):** marque a caixa **"Selecionar vários"**
   acima da lista de resultados — cada item ganha um checkbox. Marque os que
   quiser e clique em **"Baixar selecionados (N)"** para baixar todos de uma
   vez, sem precisar clicar item por item.
6. Clique em **Baixar** no resultado desejado (ou use a seleção múltipla).
   - Mods e resource packs vão direto pra pasta configurada.
   - Plugins: escolha entre "Salvar localmente" ou "Enviar para servidor Purpur"
     (esse último aparece só na aba Plugins).

## 5. Usando: Modpacks (do Modrinth)

A aba **Modpacks** busca packs publicados no Modrinth (arquivos `.mrpack`).
Clique em **Instalar** e o app baixa automaticamente todos os mods do pack para
a sua pasta de mods configurada. Uma cópia do pack também é salva em
**Meus Modpacks** para reinstalar depois.

## 6. Usando: Meus Modpacks e Meus Resource Packs (criar e compartilhar)

Essas duas abas funcionam de forma idêntica, uma para mods (`.yzk`) e outra
para resource packs (`.yzkrp`):

- **Criar um pacote seu:** vá em **Meus Modpacks** (ou **Meus Resource Packs**)
  → **Exportar como .yzk** (ou `.yzkrp`), dê um nome, e pronto.
  - O app **junta automaticamente**: (a) os itens baixados pelo próprio
    yzkModLoader durante a sessão atual, **e** (b) todos os arquivos `.jar`
    (mods) ou `.zip` (resource packs) que já estiverem na pasta configurada —
    inclusive de instâncias/sessões anteriores, mesmo que você nunca tenha
    baixado eles pelo app. Sem duplicar.
  - Os itens detectados só pela pasta (sem passar pela busca do Modrinth) são
    identificados **pelo nome do arquivo**, já que essa detecção é simples e
    não usa hash/API. Isso significa que, ao reinstalar esse pacote em outra
    máquina, esses itens específicos **não são baixados automaticamente** —
    o app avisa quais são e você precisa enviá-los manualmente junto (por
    exemplo, zipando a pasta ou mandando os arquivos separado). Já os itens
    baixados via busca do Modrinth (com ID do projeto) são reinstalados 100%
    automático em qualquer máquina.
  - O arquivo gerado fica em `~/yzkModLoader/Meus Modpacks/` (ou
    `~/yzkModLoader/Meus Resource Packs/`).
- **Compartilhar:** envie esse arquivo (`.yzk` ou `.yzkrp`) por Discord,
  WhatsApp, e-mail, qualquer meio, para quem quiser instalar o mesmo conjunto.
- **Instalar um arquivo recebido:** a pessoa só precisa ter o yzkModLoader
  instalado — ao clicar duas vezes no arquivo, o app abre direto pedindo
  confirmação para instalar o pacote. Também dá pra importar manualmente pelo
  botão **Importar de outra pessoa** em cada aba.

## 7. Associação automática das extensões `.yzk` e `.yzkrp` (pede administrador)

Na primeira vez que o app roda em uma máquina Windows (e sempre que essas
extensões ainda não estiverem associadas), ele **pede permissão de
administrador via UAC** para registrar `.yzk` e `.yzkrp` no Registro do
Windows para **todos os usuários da máquina** (`HKEY_CLASSES_ROOT`).

- Vai aparecer o prompt padrão do Windows: *"Deseja permitir que este app faça
  alterações no dispositivo?"* — aceite para habilitar a associação. Se você
  clicar em **Não**, o app continua funcionando normalmente, só sem abrir
  automaticamente ao dar duplo-clique nesses arquivos (você ainda pode
  instalar pelos botões **Importar** dentro do app).
- Isso só acontece no Windows — em outros sistemas essa etapa é ignorada
  silenciosamente.
- Se você mover o script/`.exe` de pasta depois de registrado, a associação
  vai apontar para o caminho antigo. Feche e abra o app de novo a partir do
  novo local — ele detecta e re-registra sozinho (pedindo admin de novo).
- Rodando via `python yzkModLoader.py` (arquivo `.py`), ao clicar num arquivo
  associado uma janela de terminal pode abrir por trás do app — isso é
  normal. Para evitar, use a versão `.pyw` (mesmo conteúdo, só a extensão
  muda) ou compile como `.exe` (veja seção 8).

## 8. Compilando para `.exe` com ícone personalizado

O app já está preparado para usar um ícone customizado tanto na janela quanto
no ícone do arquivo `.exe` e na associação de `.yzk`/`.yzkrp` no Windows.

1. Prepare um arquivo de ícone `icon.ico` (pode converter um `.png` em `.ico`
   em qualquer conversor online, ou com o Pillow: `Image.save("icon.ico")`).
2. Coloque `icon.ico` **na mesma pasta** do script `yzkModLoader.pyw`.
3. Instale o PyInstaller:
   ```bash
   pip install pyinstaller
   ```
4. Compile incluindo o ícone:
   ```bash
   pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --name yzkModLoader yzkModLoader.pyw
   ```
   - `--windowed`: não abre janela de terminal atrás do app.
   - `--icon=icon.ico`: define o ícone do próprio arquivo `.exe` gerado.
   - `--add-data "icon.ico;."`: garante que o `icon.ico` fica disponível ao
     lado do `.exe` final (necessário para o ícone da janela e da associação
     de arquivos funcionarem também na versão compilada). No Linux/Mac troque
     o `;` por `:` nesse parâmetro, caso compile fora do Windows.
5. O `.exe` final fica em `dist/yzkModLoader.exe`. Copie o `icon.ico` para a
   mesma pasta do `.exe` caso o `--add-data` não copie automaticamente no seu
   setup (dependendo da versão do PyInstaller você pode precisar disso como
   redundância).

Depois de compilado, ao rodar o `.exe` pela primeira vez, ele vai pedir admin
via UAC (como descrito na seção 7) e usar o `icon.ico` tanto na janela quanto
no ícone associado aos arquivos `.yzk`/`.yzkrp`.

## Observações técnicas

- A API pública do Modrinth (`api.modrinth.com/v2`) é gratuita e não exige
  autenticação para busca/download — só é usado um header `User-Agent`
  identificando o app, como a própria documentação do Modrinth recomenda.
- Modpacks do Modrinth são arquivos `.mrpack` (um zip com um manifesto
  `modrinth.index.json`); o app baixa esse arquivo, lê a lista de mods e baixa
  cada um para a pasta configurada.
- O formato `.yzk` (modpacks) e `.yzkrp` (pacotes de resource packs) do app
  são JSON simples (não é o mesmo formato `.mrpack` do Modrinth) contendo
  nome, versão do Minecraft, loader (só `.yzk`) e a lista de itens — cada item
  tem `project_id` (vazio se detectado só pela pasta), `title` e `filename`.
- Loaders suportados na busca/filtro de mods: Fabric, Forge, NeoForge e Quilt
  (via facet `categories:<loader>` da API do Modrinth). Ao instalar um modpack
  `.mrpack` do Modrinth, o loader do pack é detectado automaticamente pelo
  manifesto (`modrinth.index.json`), reconhecendo qualquer um desses quatro.
- A lista de versões do Minecraft do seletor vem do endpoint
  `/v2/tag/game_version` do Modrinth (só versões "release", sem snapshots),
  carregada uma vez ao abrir o app.
- A detecção de itens já existentes na pasta configurada (mods/resourcepacks)
  é feita **pelo nome do arquivo**, sem checar hash ou consultar a API — é
  simples e rápida, mas significa que esses itens específicos não têm
  garantia de reinstalação automática em outra máquina (veja seção 6).
- O envio para o servidor usa SFTP puro (via `paramiko`), então funciona com
  qualquer host que tenha acesso SFTP habilitado (é o padrão da maioria dos
  provedores que hospedam Purpur/Paper).
- Configurações (pastas, dados do servidor) ficam salvas localmente em
  `~/.yzkmodloader_config.json` — a senha do servidor fica salva em texto
  simples nesse arquivo, então prefira usar autenticação por chave privada se
  o seu provedor permitir.
- A associação de `.yzk`/`.yzkrp` é feita em `HKEY_CLASSES_ROOT` (todos os
  usuários da máquina), o que exige elevação de administrador via UAC toda
  vez que o app detectar que a associação ainda não existe ou está apontando
  para um caminho antigo.

## Contribuindo

Contribuições são bem-vindas! Veja [CONTRIBUTING.md](CONTRIBUTING.md) para
instruções de como rodar localmente, reportar bugs e enviar Pull Requests.

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para mais detalhes.

## Aviso

Este projeto não é afiliado ao Modrinth, Mojang, Microsoft ou aos
desenvolvedores do Purpur/Paper. É uma ferramenta independente que consome a
API pública do Modrinth conforme os termos de uso deles. Use por sua conta e
risco — verifique sempre a licença de cada mod/plugin/resource pack baixado
antes de redistribuí-lo.
