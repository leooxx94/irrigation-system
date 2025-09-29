# 🌱 Irrigation System

Un sistema di irrigazione **smart** basato su **ESP32** e **Flask (Python)**, con gestione da interfaccia web e database locale (SQLite).

---

## ✨ Funzionalità principali
- **Controllo relè** collegato all’ESP32.
- **Gestione manuale**:
  - Switch web per forzare ON/OFF.
  - Interruttore fisico collegato all’ESP32 per ignorare le schedulazioni.
- **Schedulazioni personalizzate**:
  - Più intervalli orari con precisione fino ai secondi.
  - Scelta dei giorni della settimana.
- **Interfaccia web** (Flask + HTML/CSS):
  - Configurazione del sistema.
  - Gestione orari e giorni.
  - Monitoraggio degli ultimi heartbeat inviati dall’ESP32.
- **Database SQLite** per salvare impostazioni e log heartbeat.
- **ESP32** sincronizza l’ora via NTP e scarica la configurazione dal server.
- **Heartbeat periodico**: l’ESP32 invia lo stato al server per monitoraggio.


## 🔧 Tecnologie
- **ESP32** con Arduino framework (C++).
- **Flask (Python 3)** come server web.
- **SQLite** come database locale.
- **HTML + CSS** per interfaccia semplice e responsiva.


## 🚀 Possibili utilizzi
- Irrigazione giardino o orto.
- Accensione programmata di dispositivi elettrici.
- Domotica fai-da-te.


## 📦 Installazione server (Raspberry Pi)
1. Clonare il repository:
 ```bash
 git clone https://github.com/leooxx94/irrigation-system.git
 cd irrigation-system
 ```
 
2. Creare un virtual environment ed installare le dipendenze:
```bash
 python -m venv venv
 source venv/bin/activate
 pip install -r requirements.txt
```

3. Avviare il server Flask con Waitress:
```bash
python app.py
```

4. Aprire il browser su http://<IP_RASPBERRY>:5000
