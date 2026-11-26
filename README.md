# Arqueiros Manager

Sistema de gestão da Arqueiros E-Sports com painel administrativo e bot do Telegram.

## Recursos
- Painel administrativo protegido por token.
- Painel administrativo com indicadores, elenco, competições, confrontos, títulos e auditoria.
- Cadastro, edição e retirada de jogadores, preservando histórico.
- Status do elenco: ativo, reserva, afastado e desligado, com filtro de busca.
- Indicadores de aproveitamento, saldo de gols e estatísticas individuais por competição.
- Cadastro, edição e exclusão de competições.
- Registro de títulos da equipe e títulos individuais por jogador.
- Revisão manual dos jogadores, placares, competição e correção de confrontos reconhecidos por OCR antes da aprovação.
- Registro, aprovação e rejeição de resultados.
- Ranking automático por pontos, saldo e gols.
- Registro disciplinar e recrutamento.
- Bot Telegram com comandos administrativos.
- Exportação JSON, histórico de auditoria e card PNG do ranking.
- Proteção contra possíveis confrontos duplicados (janela de 24 horas).
- Ranking e relatórios por competição.
- Relatório mensal de resultados e mural de comunicados.
- Cards individuais em PNG com estatísticas gerais ou filtradas por competição.
- Entrega semanal automática dos cards aos administradores e aos jogadores com ID do Telegram cadastrado.
- Relatório mensal de resultados.
- Relatório geral completo em PDF, com resumo da equipe, estatísticas individuais, competições, confrontos, resultados por jogador, títulos, disciplina, recrutamento e auditoria administrativa.
- Banco PostgreSQL único compartilhado entre todos os administradores: alterações feitas pelo painel ou Telegram são persistidas no mesmo banco e ficam disponíveis para os demais.
- Mural de comunicados administrativos, com envio opcional ao grupo Telegram.
- eFootball Lab: builds por jogador, progressão, boosters, overall e atributos.
- Importação de prints de atributos por OCR em português, com revisão manual antes de salvar.
- Comparação heurística de builds por posição, sem afirmar que reproduz fórmula oficial do jogo.
- Planejamento tático com formação, estilo de jogo e escalações salvas.

## Publicação no Render

### 1. Criar o serviço
1. Entre em https://dashboard.render.com/.
2. Clique em **New +** > **Web Service**.
3. Conecte o GitHub e selecione `igorjuliao78-ui/arqueiros-E-sports-manager`.
4. Selecione a branch `main`.
5. Configure:
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
6. Clique em **Create Web Service**.

> O arquivo `render.yaml` também contém a configuração do serviço. Se você criar pelo Blueprint, revise as variáveis de ambiente antes de concluir.

### 2. Configurar Environment Variables
No serviço do Render, abra **Environment** (ou **Environment Variables**) e adicione:

| Chave | Valor |
|---|---|
| `ADMIN_PANEL_TOKEN` | Uma senha longa e exclusiva para proteger o painel. |
| `TELEGRAM_BOT_TOKEN` | Token fornecido pelo @BotFather. |
| `TELEGRAM_ADMIN_IDS` | Seu ID numérico do Telegram. Pode incluir vários IDs separados por vírgula. |
| `TELEGRAM_WEBHOOK_SECRET` | Segredo aleatório contendo somente letras, números, _ ou -. |
| `DATABASE_URL` | URL de conexão PostgreSQL, se você criou um banco PostgreSQL. |
| `TEAM_CHAT_ID` | (Opcional) ID do grupo Telegram da equipe para receber comunicados publicados no painel. |
| `WEEKLY_REPORT_TOKEN` | Segredo exclusivo usado pelo workflow semanal de cards. Deve ser igual no Render e no GitHub Actions. |
| `MOBILE_AUTH_SECRET` | Segredo aleatório longo para assinar as sessões do aplicativo Android. Se omitido, o backend usa `ADMIN_PANEL_TOKEN`. |

Para produção, recomendamos criar um PostgreSQL no Render e colocar em `DATABASE_URL` a **Internal Database URL** do banco, se o banco e o serviço estiverem na mesma região. Não publique essa URL.

**Importante:** não coloque tokens ou senhas no GitHub, no código ou em mensagens. Insira os valores diretamente no painel do Render.

### 3. Fazer o primeiro deploy
1. Salve as variáveis de ambiente.
2. No Render, abra **Events** e aguarde o deploy terminar com status **Live**.
3. Abra a URL pública do serviço e acrescente `/health`. Deve aparecer um JSON com `"status":"ok"`.

### 4. Descobrir seu ID do Telegram
1. Abra seu bot no Telegram e envie `/start`.
2. Envie `/id`.
3. O bot responderá com seu ID numérico.
4. Copie esse número para `TELEGRAM_ADMIN_IDS` nas Environment Variables do Render.
5. Salve e aguarde o novo deploy/restart.

Antes de autorizar, confirme que o ID é seu. Para mais administradores, use, por exemplo, `123456789,987654321`.

### 5. Ativar o webhook
Depois que o serviço estiver **Live**, configure o webhook do Telegram. Substitua os três valores abaixo pelos seus:
- `SEU_TOKEN`: token do @BotFather.
- `SUA_URL.onrender.com`: domínio público do seu serviço Render, sem barra no final.
- `SEU_SEGREDO`: o mesmo valor configurado em `TELEGRAM_WEBHOOK_SECRET`.

No Windows PowerShell, execute:

```powershell
$TOKEN = "SEU_TOKEN"
$URL = "https://SUA_URL.onrender.com/telegram/webhook"
$SECRET = "SEU_SEGREDO"
Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" -Body @{ url = $URL; secret_token = $SECRET }
```

A resposta esperada do Telegram contém `"ok": true`. Não compartilhe o token nem publique o comando preenchido.

### 6. Testar o bot
No Telegram, abra o bot e teste:
- `/start` - mensagem inicial.
- `/id` - mostra o ID numérico do usuário.
- `/help` - lista de comandos administrativos.
- `/stats` - resumo geral.
- `/jogadores` - jogadores ativos.
- `/pendentes` - resultados aguardando aprovação.
- `/aprovar ID` - aprova um resultado pendente.
- `/rejeitar ID` - rejeita um resultado pendente.
- `/ranking` - classificação.

Os comandos administrativos só funcionam para IDs cadastrados em `TELEGRAM_ADMIN_IDS`. `/start` e `/id` ficam disponíveis para facilitar a configuração inicial.

## Painel administrativo
Acesse `https://SUA_URL.onrender.com/?token=SEU_ADMIN_PANEL_TOKEN`. O painel permite cadastrar/editar/retirar jogadores, gerenciar competições, registrar títulos, revisar confrontos e conferir estatísticas individuais. A foto do jogador pode ser enviada pelo fluxo de edição no Telegram.

Guarde o token do painel em local seguro. Não envie a URL completa com o token em grupos ou conversas públicas.

## eFootball Lab

O painel e o aplicativo Android incluem o Player Builder, OCR, comparação e planejamento tático.

### Regras de progressão implementadas
- Nível 1 começa com 0 PP; cada nível ganho concede 2 PP.
- O custo de cada categoria aumenta a cada 4 CP: CP 1–4 custam 1 PP cada; 5–8 custam 2; 9–12 custam 3; 13–16 custam 4.
- Cada CP aumenta os atributos vinculados à categoria em +1, limitado a 99 antes dos efeitos do booster.
- Os efeitos do booster são informados separadamente e aplicados depois da progressão, com teto de 120.
- O sistema não calcula o Overall Rating oficial da Konami. O otimizador usa uma heurística explícita de adequação à posição e não deve ser interpretado como OVR oficial.
- O nível máximo da carta é configurável. O simulador valida o orçamento de PP antes de salvar.
- Cartas podem ser vinculadas a um integrante da Arqueiros ou cadastradas sem vínculo.

Referências utilizadas para as regras:
- Konami — [desenvolvimento de jogadores e boosters](https://www.konami.com/efootball/en/page/overview).
- eFootball LABO — [pontos, custo progressivo e categorias de atributos](https://ef-labo.com/efootball/player-progression/). Fonte comunitária independente, não afiliada à Konami.


- Várias builds vinculadas a cada jogador.
- Posição, booster, overall opcional, pontos de progressão, atributos finais e observações.
- Importação de captura PNG/JPG/WEBP (máximo 8 MB) por OCR em português. O OCR devolve um rascunho; confira os valores e salve manualmente.
- Recomendações heurísticas por posição, com pesos transparentes. A pontuação é comparativa e interna, não uma fórmula oficial da Konami.
- Planos táticos com formação, estilo de jogo, escalação e observações.

Para a análise posicional, use chaves padronizadas em inglês, como `speed`, `acceleration`, `finishing`, `offensive_awareness`, `ball_control`, `dribbling`, `passing`, `stamina`, `defensive_awareness`, `ball_winning`, `physical_contact`, `jump`, `goalkeeping`, `reflexes`, `reach` e `catching`.

Exemplo de progressão em JSON:
```json
{"SHO":4,"PAS":8,"DRI":8,"DEX":8,"LBS":10,"STA":4}
```

As rotas usam a autenticação administrativa existente e criam suas tabelas no banco atual, sem exigir um banco separado.

## Desenvolvimento local
```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Sem `DATABASE_URL`, o projeto usa SQLite local. Em produção, use PostgreSQL persistente.

## Segurança
- Nunca coloque tokens no código ou em arquivos públicos.
- Restrinja `TELEGRAM_ADMIN_IDS` a administradores confiáveis.
- Use segredos diferentes para o painel e para o webhook.
- Se o token do bot vazar, gere outro pelo @BotFather.

## Backup automático do banco

O repositório inclui o workflow `.github/workflows/daily-database-backup.yml`, que gera um backup diário do PostgreSQL, criptografa o arquivo com AES-256 e guarda o artefato criptografado no GitHub Actions por 30 dias.

Para ativar:
1. No GitHub, abra o repositório e entre em **Settings** > **Secrets and variables** > **Actions**.
2. Clique em **New repository secret**.
3. Nome: `DATABASE_URL`.
4. Valor: use exatamente a mesma URL PostgreSQL definida em `DATABASE_URL` no serviço de produção (Neon ou outro provedor). Não crie um banco separado para o backup.
5. Salve e crie outro secret chamado `BACKUP_ENCRYPTION_PASSPHRASE`, com uma senha longa e exclusiva. Guarde essa senha em local seguro: ela será necessária para descriptografar os backups.
6. Salve. O workflow também pode ser iniciado manualmente na aba **Actions**.

**Estado verificado em 26/11/2026:** a última execução falhou porque os dois secrets ainda não estavam configurados. Até que ambos sejam adicionados e uma execução termine com sucesso, não considere o backup automático ativo.

O arquivo `.gpg` fica em **Actions** > execução do backup > **Artifacts**. Por segurança, o backup é armazenado criptografado. Para restaurar, baixe o artefato, descriptografe com a mesma senha e use `pg_restore`. Faça testes periódicos de restauração; um backup só é útil se puder ser restaurado.

## Comunicados no grupo Telegram

Para publicar comunicados do painel também em um grupo, adicione o bot ao grupo e configure `TEAM_CHAT_ID` nas variáveis de ambiente do serviço Render. Sem essa variável, o comunicado fica salvo no painel, mas não é enviado ao Telegram.

## Limites de segurança e próximos ajustes

O painel web usa o segredo `ADMIN_PANEL_TOKEN`. O aplicativo Android aceita o login administrativo `admin` com esse token ou contas administrativas criadas pela rota protegida de gestão de usuários. O backend rejeita perfis `member` e revalida o estado das contas administrativas em cada requisição. Não compartilhe o token.

## Cards semanais e entrega aos jogadores

O workflow `.github/workflows/weekly-player-cards.yml` está agendado para domingo às 23h no horário de Brasília (02h UTC de segunda-feira). Ele chama o serviço Render para gerar cards individuais atualizados.

Para ativar:
1. Gere um segredo longo e exclusivo para `WEEKLY_REPORT_TOKEN`.
2. No Render, abra o serviço `arqueiros-manager` > **Environment** e crie `WEEKLY_REPORT_TOKEN` com esse valor.
3. No GitHub, abra **Settings** > **Secrets and variables** > **Actions** > **New repository secret**.
4. Crie outro segredo chamado `WEEKLY_REPORT_TOKEN` com exatamente o mesmo valor.
5. Salve no Render e aguarde o serviço ficar **Live**. No GitHub, abra **Actions** e execute **Weekly Arqueiros Player Cards** manualmente para testar.

O workflow sempre envia todos os cards aos administradores definidos em `TELEGRAM_ADMIN_IDS`. Para o jogador também receber somente o próprio card, cadastre o ID numérico do Telegram dele no campo **ID Telegram do jogador** no painel. O jogador pode descobrir esse número enviando `/id` ao bot e repassando ao administrador. O jogador precisa ter iniciado uma conversa com o bot pelo menos uma vez para que o Telegram permita o envio.

## Corrigir confrontos pendentes pelo painel

Na tabela **Confrontos recentes**, use **Definir competição**, **Corrigir placar** e **Conferir jogadores** antes de aprovar. O sistema bloqueia a aprovação quando faltam placares gerais, competição, estatísticas individuais ou quando existe um jogador que não está ativo no elenco.

## Títulos individuais

No formulário **Registrar título**, selecione um jogador para registrar uma conquista individual. Deixe a opção de jogador sem seleção para registrar um título coletivo da equipe.



## Relatório geral em PDF
- No Telegram, qualquer administrador autorizado pode usar `/report` ou o botão **📄 Relatório Geral**.
- No painel, use **Relatório geral PDF** no cabeçalho.
- O arquivo é montado diretamente com os registros atuais do banco de dados compartilhado. O endpoint protegido é `/api/reports/full.pdf`.
- Em produção, todos os administradores devem usar a mesma instância Render e o mesmo `DATABASE_URL` do PostgreSQL; não configure bancos separados por administrador.
