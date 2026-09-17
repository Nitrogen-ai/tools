# tools

## Was das ist
- Fachübergreifende Unterrichts-/Organisationswerkzeuge (nicht fachspezifische
  Trainer — die liegen in `training`). Beispiel: `sitzplan.html`.
- Über GitHub Pages veröffentlicht: nitrogen-ai.github.io/tools/
- ClassroomSpark (Landingpage für Lehrkräfte) verlinkt hierher, genau wie auf
  `training` — Kategorie "General Tools" / "Allgemeine Werkzeuge".

## Ausnahme: goodnotes-praesentation-generator
- `goodnotes-praesentation-generator.html` ist seit 2026-09 ein echtes
  Online-Werkzeug (Diff-Modus: Aufgabenblatt- + Lösungsblatt-PDF hochladen,
  `.goodnotes`-Datei direkt im Browser erzeugen und herunterladen) — keine
  reine Erklärseite mehr, hält aber weiterhin "kein Server, keine
  Laufzeit-Netzwerkzugriffe zu Dritten" ein: es läuft komplett clientseitig
  über Pyodide (Python-in-WASM) plus einer selbst gehosteten
  PyMuPDF-WASM-Wheel, beide unter `goodnotes-assets/` in diesem Repo
  eingecheckt statt von einem CDN geladen. Kein Multi-File-Verstoß gegen die
  Ein-Datei-Konvention der übrigen Werkzeuge, sondern eine bewusste, in sich
  geschlossene Ausnahme, dokumentiert hier statt stillschweigend abzuweichen.
- Quelle der Python-Logik: `Allgemeine Materialien/_goodnotes-tools/` außerhalb
  dieses Repos (siehe dessen CLAUDE.md für die volle technische Doku zum
  .goodnotes-Format) — `goodnotes-assets/pytool/` ist eine 1:1-Kopie davon
  (Skripte + `templates/`, ohne `__pycache__`), die die HTML-Seite zur
  Laufzeit in die Pyodide-Umgebung lädt. Bei Änderungen am Quelltool: Kopie
  in `goodnotes-assets/pytool/` erneuern.
- `goodnotes-assets/pyodide/` (Pyodide-Core-Laufzeit, ~14 MB) und
  `goodnotes-assets/pymupdf-*.whl` (PyMuPDF-WASM-Wheel, ~18 MB) sind fixe
  Versionen, direkt von github.com/pyodide/pyodide bzw. pypi.org/project/pymupdf
  heruntergeladen — nur bei Bedarf (Sicherheitsupdate, Inkompatibilität)
  gegen eine neuere Version austauschen, dabei `indexURL`/Dateiname im
  `<script type="module">`-Block der HTML-Seite entsprechend anpassen.
- `goodnotes-praesentation-generator.zip` bleibt zusätzlich als
  Python-Kommandozeilenprogramm zum Download bestehen — für Farb-Modus,
  Grid-Modus und Stapelverarbeitung, die das einfache Online-Werkzeug (nur
  Diff-Modus) nicht abdeckt. Bei Änderungen am Quelltool auch dieses Zip neu
  bauen und ersetzen.

## Konventionen
- Jedes Werkzeug ist eine einzelne, offline lauffähige HTML-Datei — keine
  CDN-Abhängigkeiten, kein Server, keine Laufzeit-Netzwerkzugriffe.
- Werkzeuge werden NUR hier bearbeitet, nie in ClassroomSpark. Der Quellcode
  eines Werkzeugs (z. B. das Sitzplan-Projekt mit `npm run build`) liegt
  jeweils in einem eigenen, separaten Arbeitsverzeichnis außerhalb von
  `Schule/` — hier landet ausschließlich das fertig gebaute Auslieferungs-HTML.
- Oberflächensprache je nach Werkzeug (aktuell: Sitzplan ist Deutsch-only,
  siehe eigenes CLAUDE.md im Quellprojekt).

## Zusammenspiel
- ClassroomSpark/index.html verlinkt auf die Dateien hier (Play Online und
  Download, beides über dieselbe Datei/Domain). Neues Werkzeug hier ergänzen
  → in ClassroomSpark eine Karte in der Kategorie "General Tools" ergänzen.
- Dateinamen nicht ändern, ohne die Links in ClassroomSpark anzupassen.
- Beim Aktualisieren eines Werkzeugs: neu gebaute Datei hier einfach
  überschreiben und committen — GitHub Pages deployt automatisch bei Push auf
  `main` (siehe `.github/workflows/static.yml`).

## Öffentlich — Vorsicht
- Public Repo mit GitHub Pages. Keine personenbezogenen Daten (auch nicht in
  Testfixtures/Beispieldaten innerhalb eines Werkzeugs).
