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
- **Display:** ora e data al centro, in basso un segmento per ogni tasto con sopra il nome di ciò che comanda (ambra = acceso).
- **Tasto** → accende/spegne ciò che gli hai assegnato (luci, prese, ventilatori) o attiva una scena/script. Il display mostra nome e nuovo stato.
- **Clic sulla manopola** → passa dalla pagina 1 alla pagina 2: stessi tasti, altre assegnazioni (es. "Luci" e "PC").
- **Gira la manopola** → luminosità dell'ultima luce usata, con l'arco sul display.
- **Tieni premuta la manopola ~1 s** → QR sul display → inquadralo → scegli cosa fa ogni tasto, su entrambe le pagine, e rinomina le pagine.
- Display e LED si accendono con un tocco o una vibrazione e si spengono dopo 10 s (modificabile: *Timeout luci* nel dispositivo).
- **Display che si raddrizza da solo (opzionale):** con un accelerometro MPU6050 (SDA GPIO1, SCL GPIO2, VCC 3V3, GND) il display si gira quando metti la board di lato o capovolta, e nomi e segmenti puntano sempre verso i tasti. Senza sensore scegli la posizione a mano in **Orientamento** nel dispositivo. Se gira dalla parte sbagliata: *Correzione sensore orientamento* (0/90/180/270) o *Inverti sensore orientamento*.
- **3 o 6 tasti:** si sceglie nella pagina Macroboard. Con 6 tasti il display mostra i nomi della riga che hai usato per ultima.
- Più Macroboard in casa: ognuna ha il suo QR e la sua scheda nella pagina Macroboard.

Il telefono deve essere sulla stessa rete di Home Assistant (o collegato via Tailscale/Nabu Casa).

---

## Per chi prepara le board (Ivan)

### Compilare il firmware (una volta per versione)
Servono **entrambi** i file della cartella `firmware/` nella stessa cartella: `macroboard-kit.yaml` e `macroboard_ui.h`
(il modo più semplice: su GitHub **Code → Download ZIP**).
Se il display è montato ruotato, cambia `display_rotation` in cima al file (0 / 90 / 180 / 270).
```
cd D:\macroboard
py -V:3.13 -m esphome compile macroboard-kit.yaml
```
Alla fine il terminale stampa il percorso del file **`...factory.bin`**: è lo stesso file per tutte le board.

### Programmare ogni board
1. Collega la board al PC (porta **USB**), apri **web.esphome.io** con Chrome/Edge → **Connect** → **Install** → scegli `firmware.factory.bin`.
2. Fatto: la board è pronta per il passo 2 qui sopra. Niente Wi-Fi né chiavi dentro.

### Aggiornamenti automatici
Ogni modifica a `firmware/` viene compilata da GitHub Actions e pubblicata come **release** (alza `version` in `macroboard-kit.yaml`).
Le board (firmware ≥ 1.2.0) controllano ogni 6 ore e si aggiornano da sole. In Home Assistant il dispositivo ha anche l'entità **Firmware** con il pulsante **Installa** per aggiornare subito.
Il file `macroboard-factory.bin` di ogni release serve per programmare board nuove con web.esphome.io, senza compilare.

### Aggiornare board già installate (a mano)
`py -V:3.13 -m esphome run macroboard-kit.yaml --device <ip-della-board>` oppure dalla scheda ESPHome del dispositivo.

### Note tecniche
- Ogni board prende un nome unico: `macroboard-xxxxxx` (ultime cifre del MAC).
- La chiave di crittografia la imposta Home Assistant al primo "Configura".
- L'integrazione riconosce le board dalle entità ESPHome (`Tasto N`, `Manopola`, `Indirizzo configurazione`…): non rinominarle nel firmware.
- Il QR punta a `<indirizzo HA>/macroboard?b=<id dispositivo>`. L'indirizzo è quello in **Impostazioni → Sistema → Rete → URL locale** di Home Assistant: se il QR non si apre dal telefono, impostalo lì (es. `http://192.168.1.50:8123`) e riavvia la board.
