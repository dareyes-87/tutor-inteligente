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

## Para la defensa
- El servidor backend debe estar corriendo:
  `cd ~/tutor-inteligente && docker compose up -d`
- El dispositivo Android y la laptop deben estar en la misma red WiFi
- URL del servidor: http://192.168.100.12:8000
