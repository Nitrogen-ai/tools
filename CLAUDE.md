# tools

## Was das ist
- Fachübergreifende Unterrichts-/Organisationswerkzeuge (nicht fachspezifische
  Trainer — die liegen in `training`). Beispiel: `sitzplan.html`.
- Über GitHub Pages veröffentlicht: nitrogen-ai.github.io/tools/
- ClassroomSpark (Landingpage für Lehrkräfte) verlinkt hierher, genau wie auf
  `training` — Kategorie "General Tools" / "Allgemeine Werkzeuge".

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
