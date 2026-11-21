# Arqueiros Manager

Sistema de gestão da Arqueiros E-Sports.

## Recursos iniciais
- Painel administrativo protegido por token.
- Cadastro de jogadores e competições.
- Registro, aprovação e rejeição de resultados.
- Ranking automático por pontos, saldo e gols.
- Registro disciplinar e recrutamento.
- Bot Telegram com comandos administrativos.
- Exportação JSON e histórico de auditoria.
- Card PNG do ranking.

## Publicar no Render
1. Crie um banco PostgreSQL num provedor com plano gratuito e copie a URL.
2. No Render, crie um Web Service conectado a este repositório.
3. Build: pip install -r requirements.txt
4. Start: uvicorn app:app --host 0.0.0.0 --port $PORT
5. Configure DATABASE_URL, ADMIN_PANEL_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_IDS, TELEGRAM_WEBHOOK_SECRET.
6. Acesse /?token=SEU_ADMIN_PANEL_TOKEN.
7. Configure o webhook do Telegram: https://api.telegram.org/botTOKEN/setWebhook?url=https://SEU-SERVICO.onrender.com/telegram/webhook&secret_token=SEGREDO

## Local
pip install -r requirements.txt
uvicorn app:app --reload

Sem DATABASE_URL o app usa SQLite local. Em produção use PostgreSQL persistente.

## Segurança
Nunca coloque tokens no código ou em arquivos públicos. Use variáveis de ambiente e restrinja o acesso ao painel e ao bot.
