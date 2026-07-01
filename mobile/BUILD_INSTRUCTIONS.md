# Generar APK para la defensa

## Prerequisitos
- Cuenta en expo.dev (crear gratis en https://expo.dev)
- Node.js instalado

## Pasos

```bash
cd mobile

npm install -g eas-cli

eas login          # ingresar cuenta expo.dev

eas build --platform android --profile preview --non-interactive
```

El build tarda 10-20 minutos en los servidores de Expo.
Al terminar, EAS da un link para descargar el .apk directamente.
Instalar en el dispositivo Android: activar "Fuentes desconocidas"
en Ajustes > Seguridad, luego abrir el .apk descargado.

## URL del backend
- La app apunta al backend de **producción en Railway** (HTTPS):
  `https://tutor-inteligente-production.up.railway.app`
- Se inyecta vía `EXPO_PUBLIC_API_URL` en `eas.json` (perfil `preview`) y la lee
  `src/lib/api.ts`. Ya NO depende de una IP local ni de estar en la misma WiFi.
- Para probar contra un backend local en desarrollo, crea un archivo `.env` en
  `mobile/` con `EXPO_PUBLIC_API_URL=http://<tu-ip-local>:8000` y corre
  `npx expo start` (recuerda que HTTP local no funciona en un APK release por la
  política de cleartext de Android; para eso usa Expo Go en desarrollo).
