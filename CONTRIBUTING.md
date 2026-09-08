# Contribuindo com o yzkModLoader

Valeu por querer contribuir! Esse é um projeto simples e pessoal que virou
open source, então as regras são bem diretas.

## Como rodar localmente

```bash
git clone https://github.com/YzkModLoad/yzkModLoader.git
cd yzkModLoader
pip install -r requirements.txt
python yzkModLoader.pyw
```

## Reportando bugs

Abra uma [issue](../../issues) descrevendo:
- O que você esperava que acontecesse
- O que aconteceu de fato
- Passos pra reproduzir
- Seu sistema operacional e versão do Python (`python --version`)

## Sugerindo melhorias

Abra uma issue com a tag `enhancement` explicando a ideia antes de sair
codando — assim a gente alinha se faz sentido para o projeto antes de você
investir tempo numa PR que talvez não seja aceita.

## Enviando uma Pull Request

1. Faça um fork do repositório.
2. Crie uma branch a partir da `main`: `git checkout -b minha-feature`.
3. Faça as mudanças. Tente manter o estilo do código existente (nomes de
   variáveis e comentários em português, como o resto do projeto).
4. Teste manualmente rodando o app antes de abrir a PR — não há testes
   automatizados ainda (contribuições nessa área são bem-vindas!).
5. Abra a PR descrevendo o que mudou e por quê.

## Áreas que precisam de ajuda

- Testes automatizados (hoje o projeto não tem nenhum).
- Suporte a mais loaders além de Fabric/Forge/NeoForge/Quilt, se o Modrinth
  passar a suportar outros.
- Melhorias de UI/UX na interface customtkinter.
- Empacotamento para Linux/Mac (hoje a associação de arquivo `.yzk`/`.yzkrp`
  só funciona no Windows via Registro).

## Código de conduta

Seja respeitoso. Sem trolagem, sem discurso de ódio, sem spam. Issues e PRs
fora desse espírito serão fechadas sem aviso.
