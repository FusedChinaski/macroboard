// Macroboard – funzioni di supporto per l'interfaccia del display.
// I dati arrivano dall'integrazione Home Assistant come testo:
//   "Nome|acceso|luminosità|tipo;Nome|..."   (un blocco per tasto, 6 blocchi)
//   acceso: 1/0   luminosità: 0-100, -1 se non regolabile   tipo: t=toggle, s=scena/script, -=vuoto
#pragma once
#include <string>
#include <cstdlib>
#include <cmath>

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

// ---------------------------------------------------------------- orientamento
// o = rotazione della board vista dall'utente, in passi da 90° in senso orario:
//   0 = tasti sotto il display, 1 = tasti a sinistra, 2 = tasti sopra, 3 = tasti a destra
// Gli elementi della home vengono riposizionati in modo che i segmenti e i nomi
// puntino sempre verso i tasti, e l'ora/data si spostino dalla parte opposta.

// Ruota (x, y) di o*90° in senso orario (coordinate schermo, y verso il basso)
static inline void mb_rot(int o, int &x, int &y) {
  for (int i = 0; i < (o & 3); i++) { int t = x; x = -y; y = t; }
}

// Ricava l'orientamento dall'accelerometro (m/s²). -1 = board piatta / incerto.
static inline int mb_orient_from_accel(float ax, float ay, bool invert, int offset) {
  if (std::isnan(ax) || std::isnan(ay)) return -1;
  if (ax * ax + ay * ay < 36.0f) return -1;          // < ~6 m/s² sul piano: board quasi piatta
  if (invert) ax = -ax;
  int o;
  if (std::fabs(ax) > std::fabs(ay) * 1.3f) o = ax > 0 ? 1 : 3;
  else if (std::fabs(ay) > std::fabs(ax) * 1.3f) o = ay > 0 ? 0 : 2;
  else return -1;                                     // a 45°: non decidere
  return (o + offset) & 3;
}

static inline void mb_put(lv_obj_t *obj, int x, int y, int w = -1, lv_text_align_t al = LV_TEXT_ALIGN_CENTER) {
  if (obj == nullptr) return;
  if (w > 0) lv_obj_set_width(obj, w);
  lv_obj_set_style_text_align(obj, al, 0);
  lv_obj_align(obj, LV_ALIGN_CENTER, x, y);
}

static inline void mb_arc_angles(lv_obj_t *arc, int o, int start, int end) {
  if (arc == nullptr) return;
  lv_arc_set_bg_angles(arc, (start + 90 * o) % 360, (end + 90 * o) % 360);
}

// Dispone la home per l'orientamento o (vedi sopra)
// I widget ESPHome (label, arc) sono strutture LVGL che iniziano con lv_obj_t: basta un cast.
template<typename T> static inline lv_obj_t *mb_o(T *p) { return (lv_obj_t *) p; }

static inline void mb_layout_(int o, lv_obj_t *s1, lv_obj_t *s2, lv_obj_t *s3,
                              lv_obj_t *k1, lv_obj_t *k2, lv_obj_t *k3,
                              lv_obj_t *page, lv_obj_t *time, lv_obj_t *date, lv_obj_t *status,
                              lv_obj_t *fbn, lv_obj_t *fbs) {
  o &= 3;
  // segmenti: sempre verso i tasti
  mb_arc_angles(s1, o, 113, 143);
  mb_arc_angles(s2, o, 75, 105);
  mb_arc_angles(s3, o, 37, 67);
  // nomi dei tasti e blocco centrale
  int dx = 0, dy = 0;
  if (o == 0) {
    mb_put(k1, -54, 58, 72); mb_put(k2, 0, 80, 80); mb_put(k3, 54, 58, 72);
    mb_put(page, 0, -74, 170);
  } else if (o == 2) {
    mb_put(k1, 54, -58, 72); mb_put(k2, 0, -80, 80); mb_put(k3, -54, -58, 72);
    mb_put(page, 0, 80, 170);
    dy = 24;
  } else if (o == 1) {   // tasti a sinistra: tasto 1 in alto
    mb_put(k1, -64, -46, 60, LV_TEXT_ALIGN_LEFT); mb_put(k2, -72, 0, 60, LV_TEXT_ALIGN_LEFT);
    mb_put(k3, -64, 46, 60, LV_TEXT_ALIGN_LEFT);
    dx = 48;
    mb_put(page, dx, -74, 120);
  } else {               // tasti a destra: tasto 1 in basso
    mb_put(k1, 64, 46, 60, LV_TEXT_ALIGN_RIGHT); mb_put(k2, 72, 0, 60, LV_TEXT_ALIGN_RIGHT);
    mb_put(k3, 64, -46, 60, LV_TEXT_ALIGN_RIGHT);
    dx = -48;
    mb_put(page, dx, -74, 120);
  }
  bool side = (o & 1);
  if (time) lv_obj_align(time, LV_ALIGN_CENTER, dx, -30 + dy);
  if (date) lv_obj_align(date, LV_ALIGN_CENTER, dx, 10 + dy);
  if (status) lv_obj_align(status, LV_ALIGN_CENTER, dx, 32 + dy);
  mb_put(fbn, dx, -24 + dy, side ? 140 : 190);
  if (fbs) lv_obj_align(fbs, LV_ALIGN_CENTER, dx, 12 + dy);
}

template<typename A, typename L>
static inline void mb_layout(int o, A *s1, A *s2, A *s3, L *k1, L *k2, L *k3, L *page, L *time, L *date,
                             L *status, L *fbn, L *fbs) {
  mb_layout_(o, mb_o(s1), mb_o(s2), mb_o(s3), mb_o(k1), mb_o(k2), mb_o(k3), mb_o(page), mb_o(time),
             mb_o(date), mb_o(status), mb_o(fbn), mb_o(fbs));
}
