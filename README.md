# Macroboard – kit

Pulsantiera da scrivania per Home Assistant: ogni tasto accende/spegne una luce, la manopola ne regola la luminosità.
Le luci si scelgono dal telefono: tieni premuta la manopola, inquadra il QR sul display, scegli.

Il kit ha due parti:

| Cartella | Cos'è |
|---|---|
| `firmware/macroboard-kit.yaml` | Firmware unico per tutte le board (ESPHome) |
| `custom_components/macroboard/` | Integrazione per Home Assistant (installabile con HACS) |

---

## Per chi usa la Macroboard (3 passi)

Serve Home Assistant già funzionante.

### 1. Installa l'integrazione (una volta sola)
1. In Home Assistant apri **HACS → ⋮ in alto a destra → Repository personalizzati**.
2. Incolla `https://github.com/FusedChinaski/macroboard`, come tipo scegli **Integrazione**, premi **Aggiungi**.
3. Cerca **Macroboard** in HACS → **Scarica** → riavvia Home Assistant quando lo chiede.
4. **Impostazioni → Dispositivi e servizi → + Aggiungi integrazione → Macroboard → Invia.**
   Nella barra laterale compare la pagina **Macroboard**.

### 2. Collega la board al Wi-Fi
1. Collega la Macroboard a un caricatore USB-C (porta "USB").
2. Il display dice **Wi-Fi**: dal telefono collegati alla rete **Macroboard Setup**.
3. Si apre una pagina: scegli la tua rete, scrivi la password, **Save**.

### 3. Aggiungila a Home Assistant
1. Il display dice **Home Assistant – premi Configura**.
2. In **Impostazioni → Dispositivi e servizi** compare **Macroboard rilevata**: premi **Configura → Invia**.
3. Fatto. Il display dice "Tieni premuta la manopola per assegnare le luci".

### Uso quotidiano
- **Tieni premuta la manopola ~1 s** → QR sul display → inquadralo → scegli una luce per ogni tasto.
- **Tasto** → accende/spegne la sua luce. Il display mostra il nome della luce accanto al numero del tasto.
- **Gira la manopola** → luminosità dell'ultima luce usata. **Premi la manopola** → la accende/spegne.
- Display e LED si accendono con un tocco o una vibrazione e si spengono dopo 10 s (modificabile: *Timeout luci* nel dispositivo).
- Più Macroboard in casa: ognuna ha il suo QR e la sua scheda nella pagina Macroboard.

Il telefono deve essere sulla stessa rete di Home Assistant (o collegato via Tailscale/Nabu Casa).

---

## Per chi prepara le board (Ivan)

### Compilare il firmware (una volta per versione)
```
cd D:\macroboard
py -V:3.13 -m esphome compile macroboard-kit.yaml
```
Alla fine il terminale stampa il percorso del file **`...factory.bin`**: è lo stesso file per tutte le board.

### Programmare ogni board
1. Collega la board al PC (porta **USB**), apri **web.esphome.io** con Chrome/Edge → **Connect** → **Install** → scegli `firmware.factory.bin`.
2. Fatto: la board è pronta per il passo 2 qui sopra. Niente Wi-Fi né chiavi dentro.

### Aggiornare board già installate
`py -V:3.13 -m esphome run macroboard-kit.yaml --device <ip-della-board>` oppure dalla scheda ESPHome del dispositivo.

### Note tecniche
- Ogni board prende un nome unico: `macroboard-xxxxxx` (ultime cifre del MAC).
- La chiave di crittografia la imposta Home Assistant al primo "Configura".
- L'integrazione riconosce le board dalle entità ESPHome (`Tasto N`, `Manopola`, `Indirizzo configurazione`…): non rinominarle nel firmware.
- Il QR punta a `<indirizzo HA>/macroboard?b=<id dispositivo>`. L'indirizzo è quello in **Impostazioni → Sistema → Rete → URL locale** di Home Assistant: se il QR non si apre dal telefono, impostalo lì (es. `http://192.168.1.50:8123`) e riavvia la board.
