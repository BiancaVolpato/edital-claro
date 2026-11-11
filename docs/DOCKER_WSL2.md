# Instalar o Docker no Windows (WSL2) e validar o `docker compose`

Este guia cobre o que ficou sem verificação na Etapa 1: subir tudo com um único comando.
Vale para Windows 11 (inclusive a edição Home).

## 1. Conferir a virtualização

Abra o Gerenciador de Tarefas (`Ctrl+Shift+Esc`) → aba **Desempenho** → **CPU**. O campo
**Virtualização** deve estar **Habilitado**. Se não estiver, é preciso ativar a opção
(Intel VT-x ou AMD-V/SVM) na BIOS/UEFI do computador.

## 2. Instalar o WSL2

Abra o **PowerShell como administrador** e rode:

```powershell
wsl --install
```

Reinicie o computador quando o comando pedir. Na volta, o Ubuntu abre sozinho e pede um
nome de usuário e uma senha (são só do Linux, não da sua conta Windows).

Depois confira:

```powershell
wsl --update
```

```powershell
wsl -l -v
```

A coluna `VERSION` deve mostrar `2`.

## 3. Instalar o Docker Desktop

Baixe o instalador no site oficial, <https://www.docker.com/products/docker-desktop/>, ou
instale pelo `winget`:

```powershell
winget install -e --id Docker.DockerDesktop
```

Na instalação, mantenha marcada a opção **Use WSL 2 instead of Hyper-V**. Ao terminar,
abra o Docker Desktop, leia e aceite os termos de uso e espere o indicador no canto
inferior esquerdo mostrar **Engine running**. O Docker Desktop é gratuito para uso
pessoal e educacional.

Feche e reabra o terminal e confira:

```powershell
docker --version
```

```powershell
docker compose version
```

```powershell
docker run --rm hello-world
```

O último comando deve imprimir "Hello from Docker!".

## 4. Validar o projeto

Na pasta do projeto:

```powershell
Copy-Item .env.example .env
```

```powershell
docker compose up --build
```

A primeira execução baixa as imagens e leva alguns minutos. Quando os três serviços
estiverem de pé, confira em outro terminal:

| O que conferir | Como | Resultado esperado |
| --- | --- | --- |
| API e banco | abrir <http://localhost:8000/health> | `{"status":"ok","version":"0.1.0","database":"ok"}` |
| Frontend | abrir <http://localhost:3000> | cartão "Status do sistema" com **API: No ar** e **Banco de dados: Conectado** |
| Extensão pgvector | comando abaixo | uma linha com `vector` na lista |
| Estado dos serviços | `docker compose ps` | `db` e `backend` como `healthy` |

```powershell
docker compose exec db psql -U edital -d edital_claro -c "\dx"
```

Para encerrar, `Ctrl+C` no terminal do compose e depois:

```powershell
docker compose down
```

Use `docker compose down -v` se quiser apagar também os dados do banco.

## Se algo falhar

- **"docker: command not found"**: o Docker Desktop não está aberto, ou o terminal foi
  aberto antes da instalação. Abra o Docker Desktop e um terminal novo.
- **Porta em uso (5432, 8000 ou 3000)**: outro programa está usando a porta. Feche-o ou
  troque o lado esquerdo do mapeamento em `docker-compose.yml` (ex.: `"5433:5432"`).
- **Backend reiniciando**: rode `docker compose logs backend` e me mande a saída.
