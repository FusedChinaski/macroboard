// Macroboard – funzioni di supporto per l'interfaccia del display.
// I dati arrivano dall'integrazione Home Assistant come testo:
//   "Nome|acceso|luminosità|tipo;Nome|..."   (un blocco per tasto, 6 blocchi)
//   acceso: 1/0   luminosità: 0-100, -1 se non regolabile   tipo: t=toggle, s=scena/script, -=vuoto
#pragma once
#include <string>
#include <cstdlib>

struct MbKey {
  std::string name;
  bool on = false;
  int bri = -1;
  char type = '-';
  bool empty() const { return name.empty(); }
};

// Restituisce il campo n-esimo di s separato da sep
static inline std::string mb_field(const std::string &s, char sep, int n) {
  size_t start = 0;
  for (int i = 0; i < n; i++) {
    size_t p = s.find(sep, start);
    if (p == std::string::npos) return "";
    start = p + 1;
  }
  size_t end = s.find(sep, start);
  return s.substr(start, end == std::string::npos ? std::string::npos : end - start);
}

static inline MbKey mb_key(const std::string &data, int idx) {
  MbKey k;
  if (idx < 0) return k;
  std::string block = mb_field(data, ';', idx);
  if (block.empty()) return k;
  k.name = mb_field(block, '|', 0);
  k.on = mb_field(block, '|', 1) == "1";
  std::string b = mb_field(block, '|', 2);
  k.bri = b.empty() ? -1 : atoi(b.c_str());
  std::string t = mb_field(block, '|', 3);
  k.type = t.empty() ? 't' : t[0];
  return k;
}

static inline std::string mb_page_name(const std::string &names, int page) {
  std::string n = mb_field(names, '|', page);
  if (n.empty()) return page == 0 ? "Pagina 1" : "Pagina 2";
  return n;
}

static inline std::string mb_state_text(const MbKey &k) {
  if (k.empty()) return "nessuna azione";
  if (k.type == 's') return "attivata";
  if (!k.on) return "spenta";
  if (k.bri >= 0) return "accesa " + std::to_string(k.bri) + "%";
  return "accesa";
}

static const char *const MB_GIORNI[] = {"domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"};
static const char *const MB_MESI[] = {"gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                                      "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"};
