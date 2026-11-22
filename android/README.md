# Arqueiros App — Android nativo

Aplicativo Kotlin + Jetpack Compose conectado à API móvel autenticada do Arqueiros Manager e ao PostgreSQL já utilizado pelo bot e pelo painel.

## Build
Abra a pasta `android/` no Android Studio com JDK 17 e Android SDK 35, ou execute `gradle :app:assembleDebug`.

## Acesso
- Administrador: usuário `admin`; senha = valor de `ADMIN_PANEL_TOKEN` no Render.
- Integrantes: conta criada por um administrador no aplicativo.
- O backend deve estar atualizado com `mobile_api.py` e a variável opcional `MOBILE_AUTH_SECRET`.
