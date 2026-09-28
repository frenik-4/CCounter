# CCounter — instruktioner för Claude

## GitHub — uppdatera via PR + granskning (sedan 2026-09-28)

**Pusha ALDRIG direkt till `main`** — all kod ska gå igenom en PR, även
för egna/små ändringar, så en extern granskare (Graphite och/eller
second-opinion-mcp) hinner titta på den innan den mergas.

Graphite installerades på detta repo 2026-09-28 (via
github.com/settings/installations) och fungerar - verifierat på PR #1.
**Bekräftat samma dag: Graphite triggar INTE om automatiskt vid nya
commits på en redan öppen PR** (samma beteende som i MyHome) - ingen ny
check-run dök upp efter en uppföljningscommit. Bedöm alltså själv om en
fix efter en granskning är rimlig istället för att vänta på en ny check.

Efter varje ändring:
1. Skapa en ny branch (`git checkout -b <kort-beskrivande-namn>`)
2. Committa med ett beskrivande meddelande och `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
3. `git push -u origin <branch>` och `gh pr create` med en kort sammanfattning + testplan i PR-beskrivningen
4. Kolla om Graphite (GitHub-checken "Graphite / AI Reviews") är kopplad till detta repo och kommenterar automatiskt (`gh pr checks <nr>`). Om ingen check dyker upp inom rimlig tid är Graphite sannolikt inte installerat på `frenik-4/CCounter` - använd då `second_opinion_review`/`second_opinion_ask` (se globala instruktioner) som extern granskning istället, eller komplettera med den ändå.
5. Åtgärda relevanta påpekanden med nya commits på samma branch, verifiera igen
6. Merga (`gh pr merge <nr> --squash --delete-branch` eller enligt användarens preferens) när granskningen är klar - **merga aldrig själv utan användarens godkännande**

Detta ersätter det tidigare arbetssättet (direkta commits till `main`),
som användes för allt CCounter-arbete före 2026-09-28.

## Kameraautomation (Reolink RLC-811A)

Trafikkameran styrs delvis automatiskt via dess admin-API (separat från
RTSP-strömmen som används för själva räkningen):

- `camera_focus.py` (cron: varannan timme) - håller fokus på vägytan vid
  `main_count_line`, en försiktig "coordinate search" som bara flyttar
  fokus vid tydlig, mätbar förbättring. Hoppar över nattläge (IR).
- `camera_isp_tuning.py` (cron: var 6:e timme) - provar bildinställningar
  (exponeringsläge, motljus/WDR, brusreducering) en i taget, med en
  hälsokontroll (över-/underexponering) och en brusdetektor som måste
  godkännas innan en ändring behålls. Misslyckade/osäkra försök
  svartlistas permanent i `data/camera_isp_state.json` så de aldrig
  provas igen automatiskt.
- `reolink_client.py` - delad API-klient för båda scripten. Loggar
  alltid ut efter körning (kameran har ett tak för samtidiga sessioner -
  "max session" om man glömmer).

Se `data/camera_focus.log` och `data/camera_isp_tuning.log` för historik.
